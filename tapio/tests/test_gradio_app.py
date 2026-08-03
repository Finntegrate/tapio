"""Tests for the Gradio app module."""

from unittest.mock import Mock, patch

import pytest

from tapio.app import APP_CSS, TapioAssistantApp, main


@pytest.fixture
def test_app(mock_rag_orchestrator):
    """Create TapioAssistantApp with mocked RAG orchestrator."""
    return TapioAssistantApp(rag_orchestrator=mock_rag_orchestrator)


class TestGradioApp:
    """Tests for the Gradio app module."""

    def test_interface_uses_dark_first_visual_design(self):
        """Keep Tapio's default interface in dark mode."""
        assert "color-scheme: dark;" in APP_CSS
        assert "--body-background-fill: #0b1410;" in APP_CSS

    def test_desktop_layout_fills_the_viewport(self):
        """Keep scrolling inside the chat rather than the surrounding page."""
        assert "height: 100vh;" in APP_CSS
        assert "html, body {" in APP_CSS
        assert "overflow: hidden;" in APP_CSS
        assert "#chat-workspace {" in APP_CSS
        assert "height: max(190px, calc(100vh - 30rem)) !important;" in APP_CSS

    def test_generate_rag_response(self, test_app):
        """Test generating a RAG response."""
        test_app.rag_orchestrator.query.return_value = (
            "Test response",
            ["doc1", "doc2"],
        )
        test_app.rag_orchestrator.format_documents_for_display.return_value = "Formatted docs"

        # Call the method
        response, formatted_docs = test_app.generate_rag_response("test query")

        # Assertions
        test_app.rag_orchestrator.query.assert_called_once_with(
            query_text="test query",
            history=None,
        )
        test_app.rag_orchestrator.format_documents_for_display.assert_called_once_with(
            [
                "doc1",
                "doc2",
            ],
        )
        assert response == "Test response"
        assert formatted_docs == "Formatted docs"

    def test_respond_stream_passes_prior_history_only(self, test_app):
        """Test that respond_stream excludes the just-added current message from history."""
        prior_turns = [
            {"role": "user", "content": "What is a residence permit?"},
            {"role": "assistant", "content": "It's a document allowing you to live in Finland."},
        ]
        chat_history = list(prior_turns)

        # Consume the generator to trigger the call to the orchestrator
        list(test_app.respond_stream("How do I apply for one?", chat_history))

        test_app.rag_orchestrator.query_stream.assert_called_once_with(
            query_text="How do I apply for one?",
            history=prior_turns,
            agent_id="ilmarinen",
        )

    def test_respond_stream_shows_selected_guide(self, test_app):
        outputs = list(
            test_app.respond_stream(
                "Can you help me find a rental apartment?",
                [],
            ),
        )

        _, history, _, guide_status = outputs[-1]
        assert "**Otso**" in history[-1]["content"]
        assert "**Otso**" in guide_status
        test_app.rag_orchestrator.query_stream.assert_called_once_with(
            query_text="Can you help me find a rental apartment?",
            history=[],
            agent_id="otso",
        )

    def test_respond_stream_honours_a_manually_selected_guide(self, test_app):
        outputs = list(
            test_app.respond_stream(
                "Can you help me understand a rental agreement?",
                [],
                "rauni",
            ),
        )

        _, history, _, guide_status = outputs[-1]
        assert "**Rauni**" in history[-1]["content"]
        assert "You selected this guide." in guide_status
        test_app.rag_orchestrator.query_stream.assert_called_once_with(
            query_text="Can you help me understand a rental agreement?",
            history=[],
            agent_id="rauni",
        )

    def test_respond_stream_keeps_prior_turns_when_the_guide_changes(self, test_app):
        test_app.rag_orchestrator.query_stream.side_effect = [
            (iter(["Permit response"]), []),
            (iter(["Housing response"]), []),
        ]

        first_outputs = list(test_app.respond_stream("How do I apply for a residence permit?", []))
        prior_history = list(first_outputs[-1][1])
        second_outputs = list(test_app.respond_stream("How do I find an apartment?", prior_history))

        _, history, _, guide_status = second_outputs[-1]
        assert len(history) == 4
        assert "**Ilmarinen**" in history[1]["content"]
        assert "**Otso**" in history[3]["content"]
        assert "**Otso**" in guide_status
        assert test_app.rag_orchestrator.query_stream.call_args_list[1].kwargs == {
            "query_text": "How do I find an apartment?",
            "history": first_outputs[-1][1],
            "agent_id": "otso",
        }

    def test_respond_stream_displays_the_empty_retrieval_message(self, test_app):
        test_app.rag_orchestrator.query_stream.return_value = (iter(["Response"]), [])
        test_app.rag_orchestrator.format_documents_for_display.return_value = "No relevant documents found."

        outputs = list(test_app.respond_stream("A general question", []))

        assert outputs[-1][2] == "No relevant documents found."
        test_app.rag_orchestrator.format_documents_for_display.assert_called_with([])

    def test_generate_rag_response_with_error(self, test_app):
        """Test error handling in generate_rag_response."""
        # Setup
        test_app.rag_orchestrator.query.side_effect = Exception("Test error")

        # Call the method
        response, formatted_docs = test_app.generate_rag_response("test query")

        # Assertions
        assert "error" in response.lower()
        assert "Error retrieving" in formatted_docs

    @patch("tapio.app.TapioAssistantApp")
    def test_main_function(self, mock_app_class, mock_rag_orchestrator):
        """Test the main function that launches the Gradio app."""
        # Setup
        mock_app_instance = Mock()
        mock_app_class.return_value = mock_app_instance
        mock_app_instance.check_model_availability.return_value = True

        # Call the function
        main(rag_orchestrator=mock_rag_orchestrator, share=True)

        # Assertions
        mock_app_class.assert_called_once_with(rag_orchestrator=mock_rag_orchestrator)
        mock_app_instance.check_model_availability.assert_called_once()
        mock_app_instance.launch.assert_called_once_with(share=True)

    @patch("tapio.app.TapioAssistantApp")
    def test_main_function_model_unavailable(self, mock_app_class, mock_rag_orchestrator):
        """Test the main function when the model is unavailable."""
        # Setup
        mock_app_instance = Mock()
        mock_app_class.return_value = mock_app_instance
        mock_app_instance.check_model_availability.return_value = False

        # Call the function
        main(rag_orchestrator=mock_rag_orchestrator)

        # Assertions
        mock_app_instance.check_model_availability.assert_called_once()
        # Even with model unavailable, the app should launch
        mock_app_instance.launch.assert_called_once()
