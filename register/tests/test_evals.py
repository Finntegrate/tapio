"""The eval set has to stay honest about the register it is written against.

It is data rather than code, so nothing else would notice when a concept is
renamed or a guide's scope moves. These checks are what stop it rotting into a
set of queries that pass because they no longer assert anything.
"""

import collections

import pytest

from tapio_register import loading, paths

EVAL_PATH = paths.SERVICE_DIR / "evals" / "concept-resolution.yaml"


@pytest.fixture(scope="module")
def queries():
    # The same strict read the register gets: a duplicated key here would
    # silently drop an expected result, which is the one thing this file is for.
    return loading.load_yaml(EVAL_PATH)["queries"]


def test_every_expected_concept_exists(queries):
    known = set(loading.concepts_by_id(loading.load_register()))
    unknown = sorted({e for q in queries for e in q["expect"] if e not in known})
    assert unknown == [], f"eval set expects concepts the register does not have: {unknown}"


def test_query_ids_are_unique(queries):
    duplicated = [i for i, n in collections.Counter(q["id"] for q in queries).items() if n > 1]
    assert duplicated == []


def test_every_query_is_complete(queries):
    for query in queries:
        assert query["query"].strip()
        assert query["language"] in {"en", "fi", "sv"}
        assert query["difficulty"]
        assert isinstance(query["expect"], list)


def test_the_set_covers_the_cases_it_exists_for(queries):
    """Hard cases only would be as misleading as easy ones only."""
    difficulties = {q["difficulty"] for q in queries}
    assert {"inflection", "compound", "misspelling", "code-switch", "obsolete", "plain"} <= difficulties


def test_the_set_includes_queries_that_should_match_nothing(queries):
    """An assistant that finds a permit in every sentence is worse than one that asks."""
    silent = [q for q in queries if not q["expect"]]
    assert len(silent) >= 3
    assert {q["difficulty"] for q in silent} >= {"out-of-scope", "ambiguous"}


def test_every_language_the_register_carries_is_exercised(queries):
    assert {q["language"] for q in queries} == {"en", "fi", "sv"}


def test_obsolete_and_historical_queries_expect_a_lapsed_concept(queries):
    """The point of those cases is the register's memory, so they must use it."""
    register = loading.load_register()
    known = loading.concepts_by_id(register)
    for query in queries:
        if query["difficulty"] in {"obsolete", "historical"}:
            assert any(known[e].valid_until is not None for e in query["expect"]), query["id"]
