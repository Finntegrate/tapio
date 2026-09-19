"""Seeding produces a review queue, never register content."""

import httpx
import pytest

from tapio_register.seeding import finto

CONCEPT = "http://www.yso.fi/onto/yso/p6463"
LABELS = {"en": "residence permits", "fi": "oleskeluluvat", "sv": "uppehållstillstånd"}


@pytest.fixture
def finto_api(monkeypatch):
    """Stand in for api.finto.fi, so the tests do not reach the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            query = request.url.params["query"]
            results = [{"uri": CONCEPT}] if query == "oleskelulupa" else []
            return httpx.Response(200, json={"results": results})
        if request.url.path.endswith("/label"):
            language = request.url.params["lang"]
            if language not in LABELS:
                return httpx.Response(404)
            return httpx.Response(200, json={"prefLabel": LABELS[language]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def client(**kwargs):
        kwargs.pop("transport", None)
        return original(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return transport


def test_harvest_collects_labels_in_every_language(finto_api):
    candidates = finto.harvest(["oleskelulupa"])
    assert len(candidates) == 1
    assert candidates[0].uri == CONCEPT
    assert candidates[0].pref_label == LABELS
    assert candidates[0].matched_query == "oleskelulupa"


def test_harvest_returns_nothing_for_a_term_finto_does_not_have(finto_api):
    assert finto.harvest(["kausityötodistus"]) == []


def test_repeated_hits_are_collapsed(finto_api):
    assert len(finto.harvest(["oleskelulupa", "oleskelulupa"])) == 1


def test_candidate_file_says_it_is_not_register_content(finto_api):
    payload = finto.as_candidate_file(finto.harvest(["oleskelulupa"]), ["oleskelulupa"], "yso")
    assert payload["source"] == "finto:yso"
    assert "until a person moves it" in payload["note"]
    assert payload["candidates"][0]["reviewed"] is False


def test_missing_language_label_is_simply_absent(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"uri": CONCEPT}]})
        return httpx.Response(200, json={} if request.url.params["lang"] == "sv" else {"prefLabel": "x"})

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    candidate = finto.harvest(["oleskelulupa"])[0]
    assert set(candidate.pref_label) == {"en", "fi"}
    assert candidate.to_dict()["alt_labels"] == {}
