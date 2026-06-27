"""Gradio interface for the Tapio Assistant RAG chatbot."""

import logging
from collections.abc import Generator
from typing import Any

import gradio as gr

from tapio.services.rag_orchestrator import RAGOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TapioAssistantApp:
    """Class representing the Tapio Assistant Gradio application.

    This class provides a web interface for interacting with the RAG system.
    The RAG orchestrator is injected to enable testing and configuration.
    """

    def __init__(
        self,
        rag_orchestrator: RAGOrchestrator,
    ) -> None:
        """Initialize the Tapio Assistant application.

        Args:
            rag_orchestrator: Configured RAG orchestrator for query handling

        Example:
            >>> from tapio.factories import RAGOrchestratorFactory
            >>> from tapio.config.config_models import RAGConfig
            >>>
            >>> config = RAGConfig(llm_model_name="llama3.2")
            >>> factory = RAGOrchestratorFactory(config)
            >>> orchestrator = factory.create_orchestrator()
            >>> app = TapioAssistantApp(rag_orchestrator=orchestrator)
        """
        self.rag_orchestrator = rag_orchestrator
        self.demo = self._build_interface()

    def check_model_availability(self) -> None:
        """Check if the LLM model is available.

        Raises:
            SystemExit: If the model is not available
        """
        if not self.rag_orchestrator.check_model_availability():
            logger.error("Required LLM model is not available")
            raise SystemExit(1)

    def generate_rag_response(
        self,
        query: str,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        """Generate a response using RAG and return both the response and retrieved documents.

        Args:
            query: The user's query
            history: Chat history

        Returns:
            Tuple containing the response and formatted documents for display
        """
        try:
            # Get response and retrieved docs from the RAG orchestrator
            response, retrieved_docs = self.rag_orchestrator.query(
                query_text=query,
                history=history,
            )

            # Format documents for display
            formatted_docs = self.rag_orchestrator.format_documents_for_display(
                retrieved_docs,
            )

        except Exception:
            logger.exception("Error generating response")
            return (
                "I encountered an error while processing your query. Please try again.",
                "Error retrieving documents.",
            )
        else:
            return response, formatted_docs

    def respond_stream(
        self,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> Generator[tuple[str, list[dict[str, str]], str]]:
        """Process user message and stream the response.

        Args:
            message: User's message
            chat_history: Current chat history

        Yields:
            Tuple containing empty message (to clear input), updated chat history,
            and document display content
        """
        # Initialize chat history if empty
        if not chat_history:
            chat_history = []

        # Add user message immediately
        chat_history.append({"role": "user", "content": message})

        # Clear input and show user message
        yield "", chat_history, "Retrieving relevant documents..."

        try:
            # Get streaming response and retrieved docs from the RAG orchestrator
            # Exclude the just-appended current message; history should hold prior turns only
            response_stream, retrieved_docs = self.rag_orchestrator.query_stream(
                query_text=message,
                history=chat_history[:-1],
            )

            # Start building the assistant response and immediately start streaming
            assistant_response = "..."  # Start with ellipsis for immediate feedback
            formatted_docs = "Retrieving relevant documents..."
            first_chunk = True

            # Update chat history immediately with ellipsis to show activity
            current_history = chat_history.copy()
            current_history.append(
                {"role": "assistant", "content": assistant_response},
            )
            yield "", current_history, formatted_docs

            # Immediately start consuming the generator to trigger LLM processing
            logger.info("Starting to consume response stream")

            # Stream the response - start consuming immediately
            for chunk in response_stream:
                logger.debug("App received chunk: '%s'", chunk)
                # Replace the ellipsis with actual content on first meaningful chunk
                if first_chunk and chunk.strip():  # Only replace if chunk has content
                    logger.info(
                        "Replacing ellipsis with first meaningful chunk",
                    )
                    assistant_response = chunk
                    first_chunk = False
                elif not first_chunk:
                    # Normal streaming - append chunks
                    assistant_response += chunk
                # If first_chunk is True but chunk is empty/whitespace, keep the ellipsis

                # Update chat history with current response
                current_history = chat_history.copy()
                current_history.append(
                    {"role": "assistant", "content": assistant_response},
                )

                # Format documents for display once we have them
                if retrieved_docs and formatted_docs == "Retrieving relevant documents...":
                    formatted_docs = self.rag_orchestrator.format_documents_for_display(
                        retrieved_docs,
                    )

                yield "", current_history, formatted_docs

            # Final update with complete response
            chat_history.append(
                {"role": "assistant", "content": assistant_response},
            )

            # Ensure documents are formatted for final display
            if retrieved_docs:
                formatted_docs = self.rag_orchestrator.format_documents_for_display(
                    retrieved_docs,
                )

            yield "", chat_history, formatted_docs

        except Exception:
            logger.exception("Error in streaming response")
            error_message = "I encountered an error while processing your query. Please try again."
            chat_history.append(
                {"role": "assistant", "content": error_message},
            )
            yield "", chat_history, "Error retrieving documents."

    def clear_chat(self) -> tuple[list, str]:
        """Clear the chat history and documents display.

        Returns:
            Empty chat history and empty string for documents display
        """
        return [], ""

    def respond(
        self,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]], str]:
        """Process user message and update the chat history.

        Args:
            message: User's message
            chat_history: Current chat history

        Returns:
            Tuple containing empty message (to clear input), updated chat history,
            and document display content
        """
        # Update for 'messages' type chatbot
        if not chat_history:
            chat_history = []

        response, docs = self.generate_rag_response(message, chat_history)

        # Add the new messages
        chat_history.append({"role": "user", "content": message})
        chat_history.append({"role": "assistant", "content": response})

        return "", chat_history, docs

    def _build_interface(self) -> gr.Blocks:
        """Build the Gradio interface components.

        Returns:
            Configured Gradio Blocks interface
        """
        with gr.Blocks(title="Tapio Assistant") as demo:
            gr.Markdown("# Tapio Assistant")
            gr.Markdown(
                "Ask questions about Finnish immigration processes. "
                "The assistant uses RAG to find and use relevant information.",
            )

            with gr.Row():
                with gr.Column(scale=7):
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=500,
                    )
                    msg = gr.Textbox(
                        label="Your question",
                        placeholder="Ask about Finnish immigration processes...",
                        lines=2,
                    )

                    gr.HTML(
                        """<p style="font-size: 0.8em; color: #666; margin-top: 0.5em; margin-bottom: 0.5em;">
                            ⚠️ Disclaimer: Information provided may contain errors.
                            Always verify with official sources at <a href="https://migri.fi" target="_blank">migri.fi</a>.
                        </p>""",  # noqa: E501
                    )

                    with gr.Row():
                        submit = gr.Button("Submit")
                        clear = gr.Button("Clear")

                with gr.Column(scale=3):
                    docs_display = gr.Markdown(
                        label="Retrieved Documents",
                        value="Documents will appear here when you ask a question.",
                        height=500,
                    )

            # Define app logic - use streaming for better user experience
            # Single event handler for both submit button and Enter key
            msg.submit(
                self.respond_stream,
                [msg, chatbot],
                [
                    msg,
                    chatbot,
                    docs_display,
                ],
            )
            # Make submit button trigger the same behavior as Enter key
            submit.click(
                self.respond_stream,
                [msg, chatbot],
                [
                    msg,
                    chatbot,
                    docs_display,
                ],
            )
            clear.click(self.clear_chat, None, [chatbot, docs_display])

            # Add some example queries
            gr.Examples(
                examples=[
                    "How do I apply for a residence permit?",
                    "What documents do I need for family reunification?",
                    "How long does it take to process a work permit application?",
                    "What are the requirements for Finnish citizenship?",
                ],
                inputs=msg,
            )

        return demo

    def launch(self, share: bool = False) -> None:
        """Launch the Gradio app.

        Args:
            share: Whether to create a shareable link for the app
        """
        # Launch the Gradio app
        self.demo.launch(share=share)


def main(
    rag_orchestrator: RAGOrchestrator,
    share: bool = False,
) -> None:
    """Run the Tapio Assistant app with the specified RAG orchestrator.

    Args:
        rag_orchestrator: Configured RAG orchestrator instance
        share: Whether to create a shareable link for the app

    Example:
        >>> from tapio.factories import RAGOrchestratorFactory
        >>> from tapio.config.config_models import RAGConfig
        >>>
        >>> config = RAGConfig(llm_model_name="llama3.2")
        >>> factory = RAGOrchestratorFactory(config)
        >>> orchestrator = factory.create_orchestrator()
        >>> main(rag_orchestrator=orchestrator, share=False)
    """
    # Create the app with injected orchestrator
    app = TapioAssistantApp(rag_orchestrator=rag_orchestrator)

    # Check model availability
    app.check_model_availability()

    # Launch the app
    app.launch(share=share)


if __name__ == "__main__":
    # Create RAG orchestrator using factory for standalone execution
    from tapio.config.config_models import RAGConfig
    from tapio.factories import RAGOrchestratorFactory

    config = RAGConfig()
    factory = RAGOrchestratorFactory(config=config)
    rag_orch = factory.create_orchestrator()
    main(rag_orchestrator=rag_orch)
