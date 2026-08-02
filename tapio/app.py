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
.gradio-container {
  --body-background-fill: #0b1410;
  --body-text-color: #eaf4ec;
  --background-fill-primary: #122019;
  --background-fill-secondary: #17281f;
  --block-background-fill: #122019;
  --block-label-text-color: #dcebdd;
  --block-title-text-color: #f2f8f2;
  --border-color-primary: #2d4937;
  --input-background-fill: #101c15;
  --input-border-color: #385844;
  --input-border-color-focus: #7bd89a;
  --button-secondary-background-fill: #1a2c21;
  --button-secondary-text-color: #eaf4ec;
  --button-secondary-border-color: #3b5c46;
  max-width: 1500px !important;
  background:
    radial-gradient(circle at 12% 0%, #1a3a28 0, transparent 28rem),
    #0b1410;
  color: #eaf4ec;
  color-scheme: dark;
}
#tapio-header { margin: 0.5rem 0 1.5rem; }
#tapio-header h1 {
  color: #f1f8f2;
  font-size: 2.25rem;
  letter-spacing: -0.04em;
  margin: 0.2rem 0;
}
#tapio-header p { color: #a9bfaf; margin: 0; }
.eyebrow {
  color: #81d99c;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.11em;
}
#agent-sidebar, #guide-panel {
  background: #122019;
  border: 1px solid #2d4937;
  border-radius: 1.25rem;
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.22);
  color: #eaf4ec !important;
  color-scheme: dark;
  padding: 1.25rem;
}
#guide-panel {
  background: linear-gradient(180deg, #172b20 0%, #122019 48%);
}
#agent-sidebar *, #guide-panel * { color: #eaf4ec !important; }
#agent-sidebar a, #guide-panel a { color: #94e6ad !important; }
#agent-sidebar h3, #guide-panel h3 {
  color: #f1f8f2 !important;
  font-size: 0.95rem;
  letter-spacing: -0.01em;
  margin-bottom: 0.5rem;
}
.agent-card {
  background: #182820;
  border: 1px solid #304d3a;
  border-left: 3px solid #6dcc89;
  border-radius: 0.65rem;
  margin: 0.55rem 0;
  padding: 0.55rem 0.65rem;
}
.agent-card strong { display: block; font-size: 0.9rem; }
#agent-sidebar .agent-card small {
  color: #a8c0ae !important;
  font-size: 0.76rem;
  line-height: 1.35;
}
.agent-card--amber { border-left-color: #f0b353; }
.agent-card--nordic { border-left-color: #66c3df; }
#guide-picker { margin-top: 0.75rem; }
#guide-picker .wrap {
  display: grid !important;
  gap: 0.45rem !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
#guide-picker .wrap > label {
  align-items: center;
  background: #182820 !important;
  border: 1px solid #36533f;
  border-radius: 0.65rem;
  cursor: pointer;
  margin: 0 !important;
  min-height: 2.4rem;
  padding: 0.35rem 0.55rem;
  transition: background 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
#guide-picker .wrap > label:first-child { grid-column: 1 / -1; }
#guide-picker .wrap > label:hover {
  background: #203626 !important;
  border-color: #7dcb96;
}
#guide-picker .wrap > label:has(input:checked) {
  background: #1d412b !important;
  border-color: #7ddd9c;
  box-shadow: 0 0 0 1px #7ddd9c;
}
#guide-picker .wrap input { accent-color: #7ddd9c; }
#guide-picker .wrap span { font-size: 0.82rem; font-weight: 600; }
#active-guide {
  background: rgba(29, 65, 43, 0.72);
  border: 1px solid #3d714d;
  border-radius: 0.85rem;
  margin-bottom: 1rem;
  padding: 0.75rem 0.85rem;
}
#active-guide p { color: #c4ddca !important; font-size: 0.86rem; line-height: 1.45; }
#conversation {
  background: #101c15;
  border: 1px solid #2d4937;
  border-radius: 1.25rem;
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.2);
}
#conversation .message, #conversation .message * { color: #eaf4ec !important; }
#conversation .message.user { background: #1d412b !important; }
#conversation .message.bot { background: #1a2b20 !important; }
#message-box, #message-box .wrap { background: #101c15 !important; }
#message-box label, #message-box span { color: #d9e9dc !important; }
#message-box textarea {
  background: #101c15 !important;
  color: #f2f8f2 !important;
  border-radius: 0.85rem !important;
  min-height: 58px;
}
#message-box textarea::placeholder { color: #8ea794 !important; }
#send-button button, #send-button {
  background: #65bf80 !important;
  border-color: #7ddd9c !important;
  color: #092012 !important;
}
#send-button { border-radius: 0.75rem !important; font-weight: 650; }
#new-conversation-button button, #new-conversation-button {
  background: #1a2c21 !important;
  border-color: #3b5c46 !important;
  color: #eaf4ec !important;
}
#new-conversation-button { border-radius: 0.75rem !important; }
.disclaimer { color: #a8c0ae; font-size: 0.78rem; margin: 0.6rem 0; }
.disclaimer a { color: #94e6ad !important; }
@media (max-width: 760px) {
  #tapio-header h1 { font-size: 1.85rem; }
  #agent-sidebar, #guide-panel { padding: 1rem; }
}
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
        agent_choices = [("Auto-route", AUTO_ROUTE)] + [(agent.name, agent.id) for agent in AGENTS]

        with gr.Blocks(title="Tapio — Your guide to Finland") as demo:
            gr.HTML(
                "<div id='tapio-header'><span class='eyebrow'>FINNTEGRATE · GUIDE TEAM</span><h1>Tapio</h1>"
                "<p>Your shared conversation with Finntegrate's specialized guides.</p></div>",
            )

            with gr.Row():
                with gr.Column(scale=2, min_width=230, elem_id="agent-sidebar"):
                    gr.Markdown("### Your guide team")
                    gr.Markdown(_agent_roster_markdown())
                    gr.Markdown("### Route your question")
                    agent_selector = gr.Radio(
                        choices=agent_choices,
                        value=AUTO_ROUTE,
                        label="Choose who leads the next reply",
                        info="Or mention a guide in your message, for example @Sampo.",
                        elem_id="guide-picker",
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
                        """<p class="disclaimer">
                            ⚠️ Disclaimer: Information provided may contain errors.
                            Always verify with official sources at <a href="https://migri.fi" target="_blank">migri.fi</a>.
                        </p>""",  # noqa: E501
                    )

                    with gr.Row():
                        submit = gr.Button("Send", variant="primary", elem_id="send-button")
                        clear = gr.Button("New conversation", elem_id="new-conversation-button")

                with gr.Column(scale=3, min_width=240, elem_id="guide-panel"):
                    guide_status = gr.Markdown(
                        value=_guide_status_markdown(
                            tapio,
                            "Tapio is ready to understand what you need.",
                        ),
                        elem_id="active-guide",
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
