# Guardrails for sensitive and off-topic queries — policy

**Status:** Initial implementation

**Owner:** Finntegrate

**Related:** [PRD §7.4, safety boundary](../PRD.md#74-safety-boundary), [PRD §11, open questions](../PRD.md#11-open-questions), [crisis/escalation resource governance](crisis-escalation-resources.md), [multi-agent chat spec](multi-agent-chat.md), [issue #29](https://github.com/Finntegrate/tapio/issues/29)

## Problem statement

Tapio answers open-ended questions from people navigating an unfamiliar country, in whatever language they write in. Some of those questions are not ordinary information requests: a person may describe a personal crisis (domestic abuse, self-harm, an emergency), a legally sensitive situation (asylum, deportation, detention) where Tapio is not qualified to advise, or ask something entirely unrelated to settling in Finland. PRD §7.4 requires that Tapio recognize these and redirect rather than answer as if it were qualified to help directly. This document describes how that recognition and redirection work.

## Categories

Three categories of message get handling other than an ordinary RAG answer (`app.guardrails.GuardrailCategory`):

| Category | What it covers | Behavior |
| --- | --- | --- |
| `crisis` | Self-harm, domestic abuse, being the victim of a crime, or another situation needing immediate human help | RAG is skipped; the response points to matching entries from the [approved crisis/escalation resource list](crisis-escalation-resources.md) |
| `legal_sensitive` | Asylum, deportation, detention, and similar processes where Tapio is not a qualified adviser | RAG is skipped; the response points to legal aid and the immigration authority from the resource list |
| `out_of_scope` | Requests with no connection to settling in Finland (e.g. "write me a poem", general coding help) | RAG is skipped; the response explains Tapio's scope in the user's own language |

A message that matches more than one category (e.g. an asylum question that also expresses suicidal intent) resolves to whichever category has priority: `crisis`, then `legal_sensitive`, then `out_of_scope`. Crisis takes priority because it carries the most immediate risk.

Messages that don't match any of these categories proceed through routing and RAG exactly as before. This is a narrow, best-effort layer on top of — not a replacement for — the RAG pipeline's own honesty about unanswerable questions (PRD §7.3: "if no reliable source is found for a question, Tapio says so").

## Why an LLM classifier, not a keyword list

An earlier version of this classifier matched a fixed list of English trigger phrases with regular expressions. That approach doesn't scale: it's brittle (only catches phrasing that was anticipated ahead of time), and it's English-only in a product with no monolingual assumption about its users. `app.guardrails.LLMGuardrailClassifier` replaces it with three parallel, narrowly-scoped classification calls against the same Ollama model the RAG pipeline uses — one each for `crisis`, `legal_sensitive`, and `out_of_scope`. Each call is a focused yes/no question grounded with a handful of few-shot examples (the same illustrative phrases the old keyword list used, now shown to the model as examples rather than matched literally), which generalizes to wording and languages the examples don't literally contain. A Finnish-language message describing domestic abuse, for instance, is correctly classified even though every example in the prompt is in English.

Each check binds a Pydantic schema via LangChain's structured-output support (`ChatOllama.with_structured_output`, using Ollama's JSON-schema mode) rather than asking for free-text JSON and parsing it by hand: the model call itself is constrained to the schema, and a malformed response is a call failure to handle, not text to salvage.

This trades the keyword list's determinism for coverage, and is inherently probabilistic rather than exact. It fails open — returns no match, letting the turn proceed to a normal RAG answer — whenever a check's model call errors, times out, or can't satisfy the schema, the same degradation the RAG pipeline already has for an unreachable model. Each check is bounded by a timeout (`_CHECK_TIMEOUT_SECONDS` in `llm_classifier.py`) so a stalled Ollama call can't leave a chat's SSE stream open indefinitely with no terminal event.

A positive crisis match always resolves to at least the general `emergency` resource, even if the model returns an unrecognized or `"none"` subtype: the crisis check's `default_resource_categories` is `("emergency",)`, not empty, specifically so a schema-compliant-but-unexpected model response can never intercept a message and then surface zero contacts.

**Known limitation — total classifier failure.** If all three checks fail open at once (e.g. Ollama is fully unreachable), `classify()` returns no match and the turn proceeds to `RAGOrchestrator` unguarded. In practice this mostly coincides with RAG generation *also* failing, since both use the same Ollama connection, and the turn ends at `stream_chat_turn`'s existing generic-error path rather than producing an unguarded answer. A narrower gap is real, though, and not addressed here: if only the classifier's structured-output path fails (e.g. a schema-mode quirk) while ordinary generation still works, a crisis message could reach RAG and get an ordinary, unqualified answer. Closing that gap would mean distinguishing "classifier degraded" from "classifier said no" and deciding what degraded-mode behavior should be (block the turn? show a disclaimer?) — a deliberate design change, not addressed in this pass.

## Where it runs

The three checks run concurrently (`asyncio.gather`) and are wired into `stream_chat_turn` (`backend/app/streaming.py`), which runs them immediately after routing and before calling `RAGOrchestrator`. On a match, the turn short-circuits: no documents are retrieved, and the response comes from `app.guardrails.responses.build_guardrail_response` instead of a RAG-generated answer. An SSE `guardrail` event (`category`, `reason`) precedes the usual `citation`/`token`/`done` sequence, so a client can special-case the display later without a wire-format change today (the existing SvelteKit client already ignores unrecognized SSE event types).

**LangGraph note:** the app doesn't have a LangGraph graph yet (`CLAUDE.md`: "LangChain → LangGraph (in progress)"). The three parallel checks feeding one decision are written to be the shape a LangGraph input-classifier node is expected to take once that migration happens: parallel branches run before the routing node.

## Response text: no hardcoded user-facing string

`build_guardrail_response` has no fixed English reply for the normal path. For every guardrail interception, a small, focused, timeout-bounded LLM call (`app.prompts.guardrail_response_intro`) generates the explanatory sentence in the same language the user wrote in — Tapio can't assume every user writes in English, and the classifier itself already has to reason about non-English messages, so the reply should match. For an `out_of_scope` match, where there are no resources at stake, a failed or timed-out generation call raises; `stream_chat_turn`'s existing exception handling then reports the same generic error it already reports for any other LLM failure (e.g. an unreachable Ollama).

Resource contact details (name, phone, hours, URL) are never sent through that generation call. They're loaded and formatted deterministically from `crisis_resources.yaml` *before* the intro call runs, and appended verbatim after the generated intro, so a language-generation step can't rephrase, translate, or hallucinate a phone number or URL — those are proper nouns and contact data, not text to translate.

**Deliberate exception for crisis/legal-sensitive matches:** if the intro call fails or times out but the match has resources to show, `build_guardrail_response` does not discard them — it falls back to one fixed, English, non-LLM-generated line (`_SAFE_FALLBACK_INTRO` in `responses.py`) and still appends the resource list. This is the one hardcoded user-facing string in the guardrail response path, and it exists on purpose: losing a self-harm or domestic-abuse user's already-known emergency contacts to an unrelated LLM hiccup (a slow model, a transient Ollama error) is a worse outcome than one line of English ahead of a phone number.

## Crisis and legal-sensitive resources

Both `crisis` and `legal_sensitive` responses pull from `backend/app/config/crisis_resources.yaml`, filtered by the resource `category` values the matched check declares (e.g. a self-harm match pulls `mental_health_crisis` and `emergency` entries). See the [governance doc](crisis-escalation-resources.md) for how that file is sourced, approved, and kept current. Guide prompts and this classifier must not hardcode contact details inline — the YAML file is the only source.

**Known limitation — draft data:** as of this writing, `crisis_resources.yaml` has `status: draft` and an empty `approved_by`, per the governance doc. `app.guardrails.resources.load_crisis_resources` logs a warning whenever the loaded file's status isn't `approved`. PRD §11 marks this **blocking for broad release**: do not treat this feature as production-ready for real users in crisis until a named safety/legal/partnerships owner signs off and flips `status` to `approved`. Shipping the code is a prerequisite for that sign-off (there needs to be something to review), not a substitute for it.

By **default**, this code does **not** withhold (fail closed on) draft resources — a crisis/legal-sensitive match surfaces its matching entries regardless of `status`. The entries themselves were populated from primary-source lookups (each organization's own site, per the governance doc), not placeholders; withholding a correctly-sourced emergency number from someone in crisis, in order to satisfy a governance process that hasn't finished yet, would trade a real, immediate harm for a procedural one. The loud runtime warning plus this documented limitation are the intended control for the draft period by default — not a code-level block — and the actual production gate is the human sign-off itself.

**`BackendSettings.require_approved_crisis_resources`** (env: `TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES`, default `false`) is an explicit, deployer-controlled fail-closed path for anyone who wants a hard gate instead of the default judgment above: when set, `app.guardrails.responses._resources_for` withholds specific contact details for any category whose resource list isn't `status: approved`, and the generated intro is adjusted (via `_INTENT_DESCRIPTIONS_RESOURCES_WITHHELD`) to point the user at general emergency services instead of promising a list that won't follow. This is off by default for the reasons above — nothing has shipped to broad release yet — but the capability exists for a deployer (or a future default change made deliberately, with the named safety/legal/partnerships owner) to flip.

## Out-of-scope handling

`out_of_scope` detection is intentionally narrow: the check's few-shot examples cover a handful of clearly unrelated request shapes (creative writing, general coding help, trivia, recipes, and similar). It does not attempt to classify every possible off-topic message — that would risk false positives that block legitimate, unusually-phrased Finland questions. Anything not caught by this check falls through to the RAG pipeline, where "no reliable source found" (PRD §7.3) is the backstop for genuinely unanswerable questions.

## Testing

Guardrail behavior is covered by:

- `backend/tests/guardrails/test_llm_classifier.py` — routing/priority logic (which category wins when more than one check matches), resource-category mapping, and fail-open behavior on a model error, with the underlying structured-output call stubbed so tests don't require a live Ollama connection.
- `backend/tests/guardrails/test_resources.py` — loading and filtering the real `crisis_resources.yaml`, so a malformed edit to that file fails CI rather than only review.
- `backend/tests/guardrails/test_responses.py` — response composition: the localized intro plus deterministic resource lines, the safe-fallback-intro path (including on a simulated timeout), that a failed generation call still raises when there are no resources to fall back on, and the `require_approved_crisis_resources` gate (withheld for non-approved lists when enabled, shown for approved lists or when the gate is disabled).
- `backend/tests/routes/test_chat.py` — end-to-end SSE behavior: a guardrail match short-circuits before `RAGOrchestrator.query_stream` is ever called.

These pytest cases were also run against a real local Ollama model (`gemma4:latest`) during development, including a Finnish-language domestic-abuse message with no Finnish anywhere in the prompt's few-shot examples — it was correctly classified as `crisis`/`domestic_abuse_support`, and the generated response came back in Finnish. That confirms the multilingual behavior works beyond the mocked test suite, but is not itself part of CI (it depends on a running Ollama instance and is comparatively slow — each `classify()` call took roughly 15-45 seconds against local CPU inference in that manual run).

There is no dedicated AI evaluation harness in this repo yet (see the open items below); these pytest cases are the guardrail regression suite until one exists.

## Non-goals / open follow-ups

- **A general safety classifier.** This is a targeted layer for three specific categories, not a content-moderation system.
- **Non-emergency medical questions.** PRD §7.4 says "legal, medical, or crisis-adjacent" questions are recognized and redirected. Today, "medical" is covered only insofar as it's a medical *emergency*, matched by the `crisis` check's `emergency` subtype (e.g. "this is a medical emergency, please help me"). An ordinary medical question (dosage, symptoms, which clinic to use) is not a distinct guardrail category and proceeds through routing/RAG like any other question. Whether that gap should be closed with a fourth `medical_sensitive` category (with its own resources — a distinct scope from crisis/legal_aid) is an open product question, not resolved by this PR.
- **A dedicated AI evaluation harness.** The checklist item "add guardrail test cases to the AI evaluation dataset" is satisfied today by the pytest suite above; if/when a standalone eval dataset/harness is built for the broader RAG pipeline, these cases (including multilingual ones) should move there too.
- **Per-turn latency.** Three classification calls plus, on a match, one response-generation call are added to the affected turns. This was not benchmarked against production hardware/model choices; if it proves too slow in practice, revisit before broad release.
- **Frontend styling for the `guardrail` SSE event.** The event is emitted and safely ignored by the current client; a distinct visual treatment (e.g. for crisis resources) is a UX follow-on, not required for this backend guardrail to function.
