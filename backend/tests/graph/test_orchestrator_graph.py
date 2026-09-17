"""Tests for the LangGraph orchestrator graph (#138).

Covers the graph's node sequence (route -> retrieve -> generate) and confirms
that routing, retrieval, and generation behave exactly as they did before the
graph existed: ``AgentRouter``'s keyword-scoring logic is unchanged, and
``RAGOrchestrator``'s retrieve-then-generate sequence is unchanged, just
modeled as explicit nodes now.
"""

from unittest import mock

import pytest

from app.agents import get_agent
from app.agents.router import AUTO_ROUTE, AgentRoute, AgentRouter
from app.graph.orchestrator_graph import GENERIC_ERROR_MESSAGE, TapioOrchestratorGraph


@pytest.fixture
def orchestrator_graph(mock_doc_retrieval_service: mock.Mock, mock_llm_service: mock.Mock) -> TapioOrchestratorGraph:
    """A graph wired with a real AgentRouter and mocked retrieval/LLM services."""
    return TapioOrchestratorGraph(
        agent_router=AgentRouter(),
        doc_retrieval_service=mock_doc_retrieval_service,
        llm_service=mock_llm_service,
    )


def test_graph_runs_nodes_in_route_retrieve_generate_order(
    orchestrator_graph: TapioOrchestratorGraph, mock_doc_retrieval_service: mock.Mock, mock_llm_service: mock.Mock
) -> None:
    """The compiled graph must execute routing before retrieval before generation."""
    call_order: list[str] = []

    def route_side_effect(message: str, preferred_agent_id: str = AUTO_ROUTE) -> AgentRoute:
        call_order.append("route")
        return AgentRouter().route(message, preferred_agent_id)

    def retrieve_side_effect(_query_text: str) -> list[object]:
        call_order.append("retrieve")
        return []

    def generate_side_effect(
        *, prompt: str, system_prompt: str | None = None, history: list[dict[str, object]] | None = None
    ) -> str:
        call_order.append("generate")
        return "response"

    orchestrator_graph.agent_router.route = mock.Mock(side_effect=route_side_effect)
    mock_doc_retrieval_service.retrieve_documents.side_effect = retrieve_side_effect
    mock_llm_service.generate_response.side_effect = generate_side_effect

    orchestrator_graph.query("How do I find work?", agent_id="sampo")

    assert call_order == ["route", "retrieve", "generate"]


def test_query_ports_agent_router_keyword_scoring_unchanged(
    orchestrator_graph: TapioOrchestratorGraph, mock_llm_service: mock.Mock
) -> None:
    """Auto-routing inside the graph must select the same guide AgentRouter would alone."""
    with mock.patch("app.graph.nodes.load_prompt", return_value="prompt"):
        route, _response, _docs = orchestrator_graph.query(
            "How long does my work permit application take?",
            agent_id=AUTO_ROUTE,
        )

    assert route.agent == get_agent("ilmarinen")
    assert route.was_explicit is False
    call_args = mock_llm_service.generate_response.call_args.kwargs
    assert call_args["system_prompt"] == "prompt\n\nprompt"


def test_query_honors_explicit_agent_selection(orchestrator_graph: TapioOrchestratorGraph) -> None:
    """An explicit, non-auto agent_id must resolve to that guide, not the auto-routed one."""
    with mock.patch("app.graph.nodes.load_prompt", return_value="prompt"):
        route, _response, _docs = orchestrator_graph.query("Where should I start?", agent_id="sampo")

    assert route.agent == get_agent("sampo")
    assert route.was_explicit is True


def test_query_retrieves_documents_and_generates_a_response(
    orchestrator_graph: TapioOrchestratorGraph, mock_doc_retrieval_service: mock.Mock, mock_llm_service: mock.Mock
) -> None:
    """Retrieval and generation must still run with the query text and formatted context."""
    mock_llm_service.generate_response.return_value = "Final answer"

    with mock.patch("app.graph.nodes.load_prompt", return_value="prompt"):
        _route, response, docs = orchestrator_graph.query("Test query")

    mock_doc_retrieval_service.retrieve_documents.assert_called_once_with("Test query")
    assert response == "Final answer"
    assert docs == mock_doc_retrieval_service.retrieve_documents.return_value


def test_query_stream_preserves_streaming_behavior(
    orchestrator_graph: TapioOrchestratorGraph, mock_llm_service: mock.Mock
) -> None:
    """query_stream must return a lazily-consumed generator of the LLM's streamed chunks."""
    mock_llm_service.generate_response_stream.return_value = iter(["Hello ", "world"])

    with mock.patch("app.graph.nodes.load_prompt", return_value="prompt"):
        _route, response_stream, _docs = orchestrator_graph.query_stream("Test query")

    assert list(response_stream) == ["Hello ", "world"]


def test_query_falls_back_to_a_generic_error_on_generation_failure(
    orchestrator_graph: TapioOrchestratorGraph, mock_llm_service: mock.Mock
) -> None:
    """A node failure must not propagate; query() returns the same generic error as before."""
    mock_llm_service.generate_response.side_effect = RuntimeError("boom")

    with mock.patch("app.graph.nodes.load_prompt", return_value="prompt"):
        route, response, docs = orchestrator_graph.query("Test query", agent_id="sampo")

    assert route.agent == get_agent("sampo")
    assert response == GENERIC_ERROR_MESSAGE
    assert docs == []


def test_query_stream_falls_back_to_a_generic_error_generator_on_setup_failure(
    orchestrator_graph: TapioOrchestratorGraph, mock_doc_retrieval_service: mock.Mock
) -> None:
    """A setup failure (e.g. retrieval) must yield the same generic error message as before."""
    mock_doc_retrieval_service.retrieve_documents.side_effect = RuntimeError("boom")

    route, response_stream, docs = orchestrator_graph.query_stream("Test query", agent_id="sampo")

    assert route.agent == get_agent("sampo")
    assert list(response_stream) == [GENERIC_ERROR_MESSAGE]
    assert docs == []


def test_query_does_not_crash_on_an_unrecognized_agent_id(orchestrator_graph: TapioOrchestratorGraph) -> None:
    """An unknown agent_id fails the route node itself; the fallback must not re-raise the same error."""
    route, response, docs = orchestrator_graph.query("Test query", agent_id="not-a-real-guide")

    assert route.agent == get_agent("tapio")
    assert response == GENERIC_ERROR_MESSAGE
    assert docs == []


def test_query_stream_does_not_crash_on_an_unrecognized_agent_id(orchestrator_graph: TapioOrchestratorGraph) -> None:
    """The streaming path must have the same unrecognized-agent_id fallback as query()."""
    route, response_stream, docs = orchestrator_graph.query_stream("Test query", agent_id="not-a-real-guide")

    assert route.agent == get_agent("tapio")
    assert list(response_stream) == [GENERIC_ERROR_MESSAGE]
    assert docs == []
