# Guardrails for sensitive and off-topic queries — policy

**Status:** Initial implementation

**Owner:** Finntegrate

**Related:** [PRD §7.4, safety boundary](../PRD.md#74-safety-boundary), [PRD §11, open questions](../PRD.md#11-open-questions), [crisis/escalation resource governance](crisis-escalation-resources.md), [multi-agent chat spec](multi-agent-chat.md), [issue #29](https://github.com/Finntegrate/tapio/issues/29)

## Problem statement

Tapio answers open-ended questions from people navigating an unfamiliar country. Some of those questions are not ordinary information requests: a person may describe a personal crisis (domestic abuse, self-harm, an emergency), a legally sensitive situation (asylum, deportation, detention) where Tapio is not qualified to advise, or ask something entirely unrelated to settling in Finland. PRD §7.4 requires that Tapio recognize these and redirect rather than answer as if it were qualified to help directly. This document describes how that recognition and redirection work.

## Categories

Three categories of message get handling other than an ordinary RAG answer (`app.guardrails.GuardrailCategory`):

| Category | What it covers | Behavior |
| --- | --- | --- |
| `crisis` | Self-harm, domestic abuse, being the victim of a crime, or another situation needing immediate human help | RAG is skipped; the response points to matching entries from the [approved crisis/escalation resource list](crisis-escalation-resources.md) |
| `legal_sensitive` | Asylum, deportation, detention, and similar processes where Tapio is not a qualified adviser | RAG is skipped; the response points to legal aid and the immigration authority from the resource list |
| `out_of_scope` | Requests with no connection to settling in Finland (e.g. "write me a poem", general coding help) | RAG is skipped; the response explains Tapio's scope and suggests a general-purpose tool instead |

A message that matches more than one category (e.g. an asylum question that also expresses suicidal intent) resolves to whichever category is checked first: `crisis`, then `legal_sensitive`, then `out_of_scope`. Crisis takes priority because it carries the most immediate risk.

Messages that don't match any of these categories proceed through routing and RAG exactly as before. This is a narrow, best-effort layer on top of — not a replacement for — the RAG pipeline's own honesty about unanswerable questions (PRD §7.3: "if no reliable source is found for a question, Tapio says so").

## Where it runs

`app.guardrails.GuardrailClassifier` is a keyword-based classifier, built the same way as `app.agents.AgentRouter`: an explainable, deterministic decision with no extra LLM call, auditable from its trigger phrase list alone. It classifies the raw user message before the RAG pipeline runs.

The classifier is wired into `stream_chat_turn` (`backend/app/streaming.py`), which runs it immediately after routing and before calling `RAGOrchestrator`. On a match, the turn short-circuits: no documents are retrieved, no LLM call is made, and the response is one of the canned messages in `app.guardrails.responses`. An SSE `guardrail` event (`category`, `reason`) precedes the usual `citation`/`token`/`done` sequence, so a client can special-case the display later without a wire-format change today (the existing SvelteKit client already ignores unrecognized SSE event types).

**LangGraph note:** the app doesn't have a LangGraph graph yet (`CLAUDE.md`: "LangChain → LangGraph (in progress)"). `GuardrailClassifier.classify` is written as a small, stateless function specifically so it can become the graph's input classifier node — running before the routing node — once that migration happens, without changing its logic.

## Crisis and legal-sensitive resources

Both `crisis` and `legal_sensitive` responses pull from `backend/app/config/crisis_resources.yaml`, filtered by the resource `category` values the matched trigger declares (e.g. a self-harm trigger pulls `mental_health_crisis` and `emergency` entries). See the [governance doc](crisis-escalation-resources.md) for how that file is sourced, approved, and kept current. Guide prompts and this classifier must not hardcode contact details inline — the YAML file is the only source.

**Known limitation — draft data:** as of this writing, `crisis_resources.yaml` has `status: draft` and an empty `approved_by`, per the governance doc. `app.guardrails.resources.load_crisis_resources` logs a warning whenever the loaded file's status isn't `approved`. PRD §11 marks this **blocking for broad release**: do not treat this feature as production-ready for real users in crisis until a named safety/legal/partnerships owner signs off and flips `status` to `approved`. Shipping the code is a prerequisite for that sign-off (there needs to be something to review), not a substitute for it.

## Out-of-scope handling

`out_of_scope` detection is intentionally narrow: a fixed list of clearly unrelated request shapes (creative writing, general coding help, trivia, recipes, and similar). It does not attempt to classify every possible off-topic message — that would risk false positives that block legitimate, unusually-phrased Finland questions. Anything not caught by this narrow list falls through to the RAG pipeline, where "no reliable source found" (PRD §7.3) is the backstop for genuinely unanswerable questions.

## Testing

Guardrail behavior is covered by:

- `backend/tests/guardrails/test_classifier.py` — category assignment, word-boundary matching, and category-priority for mixed messages, parametrized with representative phrasings per category (the closest thing this project currently has to a guardrail evaluation set).
- `backend/tests/guardrails/test_resources.py` — loading and filtering the real `crisis_resources.yaml`, so a malformed edit to that file fails CI rather than only review.
- `backend/tests/guardrails/test_responses.py` — response copy composition.
- `backend/tests/routes/test_chat.py` — end-to-end SSE behavior: a guardrail match short-circuits before `RAGOrchestrator.query_stream` is ever called.

There is no dedicated AI evaluation harness in this repo yet (see the open items below); these pytest cases are the guardrail regression suite until one exists.

## Non-goals / open follow-ups

- **A general safety classifier.** This is a targeted layer for three specific categories, not a content-moderation system.
- **Multilingual trigger phrases.** Triggers are English-only for now; a non-English crisis message will likely fall through to the RAG pipeline undetected. Tracked as a gap, not solved here.
- **A dedicated AI evaluation harness.** The checklist item "add guardrail test cases to the AI evaluation dataset" is satisfied today by the pytest suite above; if/when a standalone eval dataset/harness is built for the broader RAG pipeline, these cases should move there too.
- **Frontend styling for the `guardrail` SSE event.** The event is emitted and safely ignored by the current client; a distinct visual treatment (e.g. for crisis resources) is a UX follow-on, not required for this backend guardrail to function.
