"""Harvest candidate concepts from Finto, for a person to review.

The register anchors to published Finnish vocabularies rather than minting
identifiers by preference, and Finto (the National Library's vocabulary service,
no API key) is where YSO and JUPO live.

What this produces is a *candidate queue*, never register content. YSO is a
general-purpose ontology whose immigration coverage is uneven, so a machine
cannot decide which of its concepts is the right anchor for a Finnish
administrative specific - that judgement is the review pass, and it is the
difference between an authorized identifier register and one more scraped list.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

FINTO_API = "https://api.finto.fi/rest/v1"
LANGUAGES = ("en", "fi", "sv")


@dataclass
class Candidate:
    """One external concept that might anchor a register entry."""

    uri: str
    vocabulary: str
    pref_label: dict[str, str] = field(default_factory=dict)
    alt_labels: dict[str, list[str]] = field(default_factory=dict)
    matched_query: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Render for the candidate file a reviewer reads."""
        return {
            "uri": self.uri,
            "vocabulary": self.vocabulary,
            "matched_query": self.matched_query,
            "pref_label": self.pref_label,
            "alt_labels": {language: labels for language, labels in self.alt_labels.items() if labels},
            "reviewed": False,
        }


def _search(client: httpx.Client, query: str, vocabulary: str, language: str) -> list[str]:
    response = client.get(
        f"{FINTO_API}/search",
        params={"query": query, "vocab": vocabulary, "lang": language},
    )
    response.raise_for_status()
    return [result["uri"] for result in response.json().get("results", [])]


def _labels(client: httpx.Client, uri: str, vocabulary: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return the preferred and alternative labels a vocabulary holds for a concept."""
    pref: dict[str, str] = {}
    alt: dict[str, list[str]] = {}
    for language in LANGUAGES:
        response = client.get(f"{FINTO_API}/{vocabulary}/label", params={"uri": uri, "lang": language})
        if response.status_code != httpx.codes.OK:
            continue
        payload = response.json()
        label = payload.get("prefLabel")
        if label:
            pref[language] = label
        # Alternative labels are what tell a reviewer whether a candidate is the
        # right anchor - they are the other surface forms people actually use -
        # so they are carried through rather than dropped. Finto returns either
        # a list or, for a single label, a bare string.
        others = payload.get("altLabel") or []
        others = [others] if isinstance(others, str) else list(others)
        if others:
            alt[language] = others
    return pref, alt


def harvest(
    queries: list[str],
    vocabulary: str = "yso",
    language: str = "fi",
    timeout: float = 20.0,
) -> list[Candidate]:
    """Search Finto for each query and return the concepts found, with labels."""
    found: dict[str, Candidate] = {}
    with httpx.Client(timeout=timeout, headers={"User-Agent": "tapio-register/0.1"}) as client:
        for query in queries:
            for uri in _search(client, query, vocabulary, language):
                if uri in found:
                    continue
                pref, alt = _labels(client, uri, vocabulary)
                found[uri] = Candidate(
                    uri=uri,
                    vocabulary=vocabulary,
                    pref_label=pref,
                    alt_labels=alt,
                    matched_query=query,
                )
    return list(found.values())


def as_candidate_file(candidates: list[Candidate], queries: list[str], vocabulary: str) -> dict[str, Any]:
    """Wrap candidates with enough context for a reviewer to judge them later."""
    return {
        "harvested_on": date.today().isoformat(),  # noqa: DTZ011 - a harvest is dated by calendar day
        "source": f"finto:{vocabulary}",
        "api": FINTO_API,
        "queries": queries,
        "note": (
            "Candidates only. Nothing here is part of the register until a person moves it into "
            "the matching file under tapio_register/data/ with its own observation provenance."
        ),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
