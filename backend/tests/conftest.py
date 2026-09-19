"""Shared fixtures for backend tests: RAG/agent unit tests and the FastAPI API tests."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_ollama import ChatOllama

from app.agents.router import AgentRouter
from app.dependencies import get_guardrail_classifier, get_orchestrator, get_orchestrator_graph
from app.graph.orchestrator_graph import TapioOrchestratorGraph
from app.guardrails import GuardrailClassifierProtocol, LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult
from app.main import app

# ============================================================================
# Mock fixtures for RAG/agent unit tests
# ============================================================================


@pytest.fixture
def mock_embeddings():
    """Mock HuggingFace embeddings for fast unit tests.

    Returns a mock with embed_query and embed_documents methods that return
    consistent dummy embeddings without loading a real model.
    """
    embeddings = Mock()
    # Typical embedding dimension for all-MiniLM-L6-v2 is 384
    dummy_embedding = [0.1] * 384

    embeddings.embed_query.side_effect = lambda _: dummy_embedding.copy()

    def embed_documents_mock(texts):
        return [dummy_embedding.copy() for _ in texts]

    embeddings.embed_documents.side_effect = embed_documents_mock
    return embeddings


@pytest.fixture
def mock_chroma_store():
    """Mock ChromaRetriever for unit tests."""
    store = Mock()
    store.query.return_value = []
    store.add_document.return_value = None
    store.add_documents.return_value = None
    return store


@pytest.fixture
def mock_llm_service():
    """Mock BaseChatModel (a LangChain chat model) for unit tests."""
    model = Mock(spec=BaseChatModel)
    model.invoke.return_value = AIMessage(content="Mocked LLM response")
    model.stream.return_value = iter(
        [AIMessageChunk(content="Mocked "), AIMessageChunk(content="streamed "), AIMessageChunk(content="response")],
    )
    return model


@pytest.fixture
def mock_doc_retrieval_service():
    """Mock DocumentRetrievalService for unit tests."""
    service = Mock()

    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source": "test.md", "url": "https://example.com"}

    service.retrieve_documents.return_value = [mock_doc]
    service.format_documents_as_context.return_value = "Test document content"
    return service


@pytest.fixture
def tmp_chroma_db(tmp_path):
    """Temporary directory for ChromaDB in integration tests."""
    db_dir = tmp_path / "chroma_db"
    db_dir.mkdir()
    return str(db_dir)


def pytest_configure(config):
    """Add custom markers for pytest."""
    config.addinivalue_line("markers", "integration: mark test as integration test (uses real embeddings, slower)")


@pytest.fixture(autouse=True)
def _stub_guardrail_intro_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent guardrail intro generation from building a real chat model.

    ``build_guardrail_response`` (see ``app.guardrails.responses``) builds its own
    short-timeout model per call rather than taking an injected one, so — unlike the RAG
    generation path, which is always exercised through an injected mock — nothing else
    stops a test that reaches it (e.g. a ``/chat/stream`` guardrail-interception test)
    from constructing a real provider client and trying to reach it over the network.
    Autouse so this is safe by default; ``tests/guardrails/test_responses.py`` overrides
    it per test to control the generated intro text.
    """
    model = Mock(spec=BaseChatModel)
    model.invoke.return_value = AIMessage(content="Mocked guardrail intro.")
    monkeypatch.setattr("app.guardrails.responses.build_chat_model", lambda *_args, **_kwargs: model)


# ============================================================================
# Fixtures for the FastAPI API tests
# ============================================================================


@pytest.fixture
def mock_rag_orchestrator() -> Mock:
    """Fake RAGOrchestrator whose query_stream returns a finite token stream."""
    orchestrator = Mock()
    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source_url": "https://example.com", "title": "Example source"}

    orchestrator.query_stream.return_value = (iter(["Mocked ", "response"]), [mock_doc])
    orchestrator.check_model_availability.return_value = True
    return orchestrator


@pytest.fixture
def fake_agent_router() -> AgentRouter:
    """Real AgentRouter — pure and deterministic, no need to fake it."""
    return AgentRouter()


@pytest.fixture
def mock_orchestrator_graph(fake_agent_router: AgentRouter) -> Mock:
    """Fake TapioOrchestratorGraph whose query_stream returns a finite token stream.

    Its ``safe_route`` delegates to a real ``AgentRouter`` (pure and
    deterministic, see ``fake_agent_router``) since ``stream_chat_turn`` calls
    it directly for the turn's routing event.

    Args:
        fake_agent_router: Real, deterministic ``AgentRouter`` to back
            ``graph.agent_router`` and ``graph.safe_route``.

    Returns:
        A ``Mock`` standing in for ``TapioOrchestratorGraph``, with
        ``agent_router``, ``safe_route``, ``query_stream``, and
        ``check_model_availability`` preconfigured.
    """
    graph = Mock()
    graph.agent_router = fake_agent_router
    # Delegates to a real graph's safe_route (rather than re-deriving its unknown-agent_id
    # fallback here) so a test exercising that fallback exercises the real behavior.
    graph.safe_route.side_effect = TapioOrchestratorGraph(
        agent_router=fake_agent_router,
        doc_retrieval_service=Mock(),
        llm_service=Mock(),
    ).safe_route
    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source_url": "https://example.com", "title": "Example source"}

    graph.query_stream.return_value = (None, iter(["Mocked ", "response"]), [mock_doc])
    graph.check_model_availability.return_value = True
    return graph


@pytest.fixture
def fake_guardrail_classifier() -> GuardrailClassifierProtocol:
    """A real LLMGuardrailClassifier with its structured model call stubbed.

    Constructing ``LLMGuardrailClassifier`` doesn't touch the network (the
    ``ChatOllama`` binding is lazy), so the classifier's own routing/priority
    logic runs for real; only the underlying model call is replaced, keyed
    off which check's prompt it receives so route/streaming tests stay
    deterministic without a live Ollama connection. Recognizes exactly the
    two phrasings used in ``tests/routes/test_chat.py``'s guardrail tests;
    ``LLMGuardrailClassifier`` itself is covered more broadly in
    ``tests/guardrails/test_llm_classifier.py``.
    """
    classifier = LLMGuardrailClassifier(ChatOllama(model="test-model"))

    async def fake_ainvoke(prompt: str) -> GuardrailCheckResult:
        # The few-shot examples baked into every check's own prompt can themselves
        # contain trigger phrases (e.g. the crisis check's own example text mentions
        # "kill myself"), so only the actual message section is checked for a match.
        message_section = prompt.rsplit("BEGIN MESSAGE TO CLASSIFY", 1)[-1]
        if "self-harm or" in prompt and "kill myself" in message_section:
            return GuardrailCheckResult(match=True, subtype="self_harm", reason="Message expresses self-harm intent.")
        if "completely unrelated" in prompt and "poem" in message_section:
            return GuardrailCheckResult(match=True, subtype="none", reason="Off-topic creative writing request.")
        return GuardrailCheckResult(match=False, subtype="none", reason="")

    classifier._structured_model = SimpleNamespace(ainvoke=fake_ainvoke)
    return classifier


@pytest.fixture
def client(
    mock_rag_orchestrator: Mock,
    mock_orchestrator_graph: Mock,
    fake_guardrail_classifier: GuardrailClassifierProtocol,
) -> Iterator[TestClient]:
    """TestClient with the orchestrator/graph/classifier dependencies overridden.

    Deliberately not entered as a context manager, so the real lifespan
    (which builds a real RAGOrchestrator against Ollama/Chroma) never runs
    during tests.
    """
    app.dependency_overrides[get_orchestrator] = lambda: mock_rag_orchestrator
    app.dependency_overrides[get_orchestrator_graph] = lambda: mock_orchestrator_graph
    app.dependency_overrides[get_guardrail_classifier] = lambda: fake_guardrail_classifier
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
