"""Gradio interface for the Tapio Assistant RAG chatbot."""

import logging
from collections.abc import Generator
from typing import Any, cast

import gradio as gr

from tapio.agents import AGENTS, AUTO_ROUTE, AgentDefinition, AgentRouter
from tapio.services.rag_orchestrator import RAGOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_CSS = """
.gradio-container { max-width: 1500px !important; }
#tapio-header { margin-bottom: 0.5rem; }
#tapio-header h1 { margin-bottom: 0.25rem; }
#agent-sidebar, #guide-panel {
  background: #f8faf9;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  color: #17201a !important;
  color-scheme: light;
  padding: 1rem;
}
#agent-sidebar *, #guide-panel * { color: #17201a !important; }
#agent-sidebar a, #guide-panel a { color: #176b46 !important; }
#agent-sidebar input, #agent-sidebar button { background: #ffffff !important; }
#conversation { border: 1px solid #e5e7eb; border-radius: 1rem; }
#message-box textarea { min-height: 58px; }
.agent-card { border-left: 3px solid #2f6b4f; margin: 0.7rem 0; padding-left: 0.7rem; }
.agent-card--amber { border-color: #d88d1a; }
.agent-card--nordic { border-color: #28708c; }
"""


def _agent_roster_markdown() -> str:
    """Render a compact guide directory for the app sidebar."""
    cards = []
    for agent in AGENTS:
        responsibilities = ", ".join(agent.responsibilities[:2])
        cards.append(
            f'<div class="agent-card agent-card--{agent.color}">'
            f"<strong>{agent.name}</strong> · {agent.title}<br>"
            f"<small>{responsibilities}</small>"
            "</div>",
        )
    return "\n".join(cards)


def _guide_status_markdown(agent: AgentDefinition, reason: str) -> str:
    """Render the active guide's scope and the visible routing explanation."""
    focus = ", ".join(agent.responsibilities)
    return f"""### Active guide
**{agent.name}** · {agent.title}

{reason}

**Focus:** {focus}

_Information is grounded in retrieved official sources. Verify important decisions with the relevant authority._"""


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
            >>> config = RAGConfig(llm_model_name="gemma4:latest")
            >>> factory = RAGOrchestratorFactory(config)
            >>> orchestrator = factory.create_orchestrator()
            >>> app = TapioAssistantApp(rag_orchestrator=orchestrator)
        """
        self.rag_orchestrator = rag_orchestrator
        self.agent_router = AgentRouter()
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
        agent_id: str = "tapio",
    ) -> tuple[str, str]:
        """Generate a response using RAG and return both the response and retrieved documents.

        Args:
            query: The user's query
            history: Chat history
            agent_id: The guide whose specialist prompt should be applied

        Returns:
            Tuple containing the response and formatted documents for display
        """
        try:
            # Get response and retrieved docs from the RAG orchestrator
            query_args: dict[str, Any] = {"query_text": query, "history": history}
            if agent_id != "tapio":
                query_args["agent_id"] = agent_id
            response, retrieved_docs = self.rag_orchestrator.query(**query_args)

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
        selected_agent_id: str = AUTO_ROUTE,
    ) -> Generator[tuple[str, list[dict[str, str]], str, str]]:
        """Process user message and stream the response.

        Args:
            message: User's message
            chat_history: Current chat history
            selected_agent_id: User-selected guide or automatic routing mode

        Yields:
            Tuple containing cleared message input, updated chat history, source
            display content, and the active-guide panel.
        """
        # Initialize chat history if empty
        if not chat_history:
            chat_history = []

        route = self.agent_router.route(message, selected_agent_id)
        agent = route.agent
        guide_status = _guide_status_markdown(agent, route.reason)
        agent_header = f"**{agent.name}** · {agent.title}\n\n"

        # Add user message immediately
        chat_history.append({"role": "user", "content": message})

        # Clear input and show user message
        yield "", chat_history, "Retrieving relevant official sources...", guide_status

        try:
            # Get streaming response and retrieved docs from the RAG orchestrator
            # Exclude the just-appended current message; history should hold prior turns only
            query_args: dict[str, Any] = {"query_text": message, "history": chat_history[:-1]}
            if agent.id != "tapio":
                query_args["agent_id"] = agent.id
            response_stream, retrieved_docs = self.rag_orchestrator.query_stream(**query_args)

            # Start building the assistant response and immediately start streaming
            assistant_response = f"{agent_header}…"
            formatted_docs = "Retrieving relevant official sources..."
            first_chunk = True

            # Update chat history immediately with ellipsis to show activity
            current_history = chat_history.copy()
            current_history.append(
                {"role": "assistant", "content": assistant_response},
            )
            yield "", current_history, formatted_docs, guide_status

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
                    assistant_response = f"{agent_header}{chunk}"
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
                if retrieved_docs and formatted_docs == "Retrieving relevant official sources...":
                    formatted_docs = self.rag_orchestrator.format_documents_for_display(
                        retrieved_docs,
                    )

                yield "", current_history, formatted_docs, guide_status

            # Final update with complete response
            chat_history.append(
                {"role": "assistant", "content": assistant_response},
            )

            # Ensure documents are formatted for final display
            if retrieved_docs:
                formatted_docs = self.rag_orchestrator.format_documents_for_display(
                    retrieved_docs,
                )

            yield "", chat_history, formatted_docs, guide_status

        except Exception:
            logger.exception("Error in streaming response")
            error_message = "I encountered an error while processing your query. Please try again."
            chat_history.append(
                {"role": "assistant", "content": error_message},
            )
            yield "", chat_history, "Error retrieving official sources.", guide_status

    def clear_chat(self) -> tuple[list, str, str]:
        """Clear the chat history and documents display.

        Returns:
            Empty chat history, initial source copy, and Tapio's guide panel
        """
        tapio = self.agent_router.route("").agent
        return (
            [],
            "Sources will appear here with each response.",
            _guide_status_markdown(
                tapio,
                "Tapio is ready to understand what you need.",
            ),
        )

    def respond(
        self,
        message: str,
        chat_history: list[dict[str, str]],
        selected_agent_id: str = AUTO_ROUTE,
    ) -> tuple[str, list[dict[str, str]], str]:
        """Process user message and update the chat history.

        Args:
            message: User's message
            chat_history: Current chat history
            selected_agent_id: User-selected guide or automatic routing mode

        Returns:
            Tuple containing empty message (to clear input), updated chat history,
            and document display content
        """
        # Update for 'messages' type chatbot
        if not chat_history:
            chat_history = []

        route = self.agent_router.route(message, selected_agent_id)
        response, docs = self.generate_rag_response(message, chat_history, route.agent.id)

        # Add the new messages
        chat_history.append({"role": "user", "content": message})
        chat_history.append(
            {
                "role": "assistant",
                "content": f"**{route.agent.name}** · {route.agent.title}\n\n{response}",
            },
        )

        return "", chat_history, docs

    def _build_interface(self) -> gr.Blocks:
        """Build the Gradio interface components.

        Returns:
            Configured Gradio Blocks interface
        """
        tapio = self.agent_router.route("").agent
        agent_choices = [("Tapio chooses the right guide", AUTO_ROUTE)] + [
            (f"{agent.name} — {agent.title}", agent.id) for agent in AGENTS
        ]

        with gr.Blocks(title="Tapio — Your guide to Finland") as demo:
            gr.HTML(
                "<div id='tapio-header'><h1>Tapio</h1>"
                "<p>Your shared conversation with Finntegrate's specialized guides.</p></div>",
            )

            with gr.Row():
                with gr.Column(scale=2, min_width=230, elem_id="agent-sidebar"):
                    gr.Markdown("### Your guide team")
                    gr.Markdown(_agent_roster_markdown())
                    agent_selector = gr.Dropdown(
                        choices=agent_choices,
                        value=AUTO_ROUTE,
                        label="Choose a guide",
                        info="You can also mention a guide, for example @Sampo.",
                    )

                with gr.Column(scale=7, min_width=360):
                    gr.Markdown("### # your-finland-journey")
                    chatbot = gr.Chatbot(
                        show_label=False,
                        height=560,
                        layout="bubble",
                        buttons=["copy_all"],
                        feedback_options=None,
                        placeholder="Start with a question. Tapio will bring in the right guide when needed.",
                        elem_id="conversation",
                    )
                    msg = gr.Textbox(
                        label="Message Tapio and the guides",
                        placeholder="For example: How do I apply for a residence permit?",
                        lines=2,
                        elem_id="message-box",
                    )

                    gr.HTML(
                        """<p style="font-size: 0.8em; color: #666; margin-top: 0.5em; margin-bottom: 0.5em;">
                            ⚠️ Disclaimer: Information provided may contain errors.
                            Always verify with official sources at <a href="https://migri.fi" target="_blank">migri.fi</a>.
                        </p>""",  # noqa: E501
                    )

                    with gr.Row():
                        submit = gr.Button("Send", variant="primary")
                        clear = gr.Button("New conversation")

                with gr.Column(scale=3, min_width=240, elem_id="guide-panel"):
                    guide_status = gr.Markdown(
                        value=_guide_status_markdown(
                            tapio,
                            "Tapio is ready to understand what you need.",
                        ),
                    )
                    gr.Markdown("### Sources in this response")
                    docs_display = gr.Markdown(
                        value="Sources will appear here with each response.",
                    )

            # Define app logic - use streaming for better user experience
            # Single event handler for both submit button and Enter key
            cast("Any", msg).submit(
                self.respond_stream,
                [msg, chatbot, agent_selector],
                [
                    msg,
                    chatbot,
                    docs_display,
                    guide_status,
                ],
            )
            # Make submit button trigger the same behavior as Enter key
            cast("Any", submit).click(
                self.respond_stream,
                [msg, chatbot, agent_selector],
                [
                    msg,
                    chatbot,
                    docs_display,
                    guide_status,
                ],
            )
            cast("Any", clear).click(self.clear_chat, None, [chatbot, docs_display, guide_status])

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
        self.demo.launch(share=share, css=APP_CSS)


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
        >>> config = RAGConfig(llm_model_name="gemma4:latest")
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
