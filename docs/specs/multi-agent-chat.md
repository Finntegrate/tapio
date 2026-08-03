# Multi-agent chat experience — feature specification

**Status:** Initial implementation

**Owner:** Finntegrate

**Related architecture:** [ADR 0005](../ADRs/0005-multi-agent-chat-experience.md)

## Problem statement

People moving to Finland often need help across several connected topics—permits, employment, benefits, and housing—but the current chat presents every answer as one anonymous assistant. Users cannot tell what expertise is being applied, why a response is being routed, or how to continue when their needs cross domains. This weakens confidence in a high-stakes context and makes a coordinated specialist model invisible.

The feature serves people navigating life in Finland, especially newcomers who need concise, multilingual-friendly guidance anchored in official sources. It also gives Finntegrate a clear interaction model to evaluate before investing in durable multi-agent orchestration.

## Goals

1. Make each response visibly attributable to Tapio or one of the initial specialized guides.
2. Let a user either rely on transparent automatic routing or choose/mention a guide directly.
3. Keep a person's journey in one chronological conversation, without asking them to restate their situation between guides.
4. Keep source material visible beside the answer so users can verify high-impact information with official services.
5. Establish a stable definition and prompt contract that the future LangGraph router can adopt without changing the user experience.

## Non-goals

- **Autonomous multi-agent debate:** Multiple agents will not independently discuss every message. It adds noise, cost, and ambiguity without helping the user.
- **Permanent agent rooms:** The v1 is not a collection of specialist channels. A shared journey is more important than chat-room fidelity.
- **Persistent saved conversations:** This depends on authentication and durable checkpoints; it is covered by [#16](https://github.com/Finntegrate/tapio/issues/16) and [#35](https://github.com/Finntegrate/tapio/issues/35).
- **Full frontend feature parity:** The SvelteKit `app/` client (see [ADR 0006](../ADRs/0006-retire-gradio.md)) replaces the retired Gradio prototype, but `@mention`-style guide selection and broader test coverage are a fast-follow, not part of the initial build.
- **Legal, medical, or crisis support:** The feature must not impersonate a professional service. A dedicated safety classifier and escalation policy remain required before broad release ([#29](https://github.com/Finntegrate/tapio/issues/29)).

## Initial guide definitions

| Guide | User-facing role | In scope |
| --- | --- | --- |
| **Tapio** | Forest guide and coordinator | Clarification, routing, handoffs, and cross-guide summaries |
| **Ilmarinen** | Craftsman of documentation | Residence permits, visas, applications, and official paperwork |
| **Sampo** | Prosperity guide | Job search, networking, career pathways, and workplace culture |
| **Rauni** | Prosperity guardian | Kela, social security, benefits, and family support |
| **Otso** | Housing guardian | Housing, rental agreements, tenant rights, and settlement |

The public Tapio page is the canonical source for these roles. Sampo is an employment and career guide, not a financial-requirements agent.

## User stories

### Newcomer seeking guidance

- As a newcomer, I want Tapio to select the relevant guide when I ask a question so that I can receive focused help without knowing the organization first.
- As a newcomer, I want to see who is answering and why they were selected so that I can understand the guidance's scope.
- As a newcomer, I want to choose or mention a guide directly so that I can steer the conversation when I know the area I need help with.
- As a newcomer, I want sources displayed with the answer so that I can verify important information before acting.

### Returning user

- As a returning user, I want later guides to respond in the same conversation so that I do not need to repeat my story when a question changes topic.

### Safety-sensitive user

- As a user with a question beyond Tapio's remit, I want an honest boundary and appropriate official or human support so that I am not misled by an AI answer.

## Requirements

### Must-have (P0)

#### Shared conversation with visible guide identity

- The primary screen presents one chronological conversation labelled as the user's Finland journey.
- Each assistant message begins with the active guide's name and role.
- The active-guide panel states the selected guide, its responsibilities, and the routing reason.

##### Shared conversation acceptance criteria

- [ ] Given a response is generated, when it is shown in the conversation, then the reader can identify the guide without opening another panel.
- [ ] Given Tapio selects a specialist, when the response begins, then the active-guide panel explains the selection in plain language.
- [ ] Given a user changes topic, when a different guide is selected, then previous messages remain visible in the same conversation.

#### Transparent routing and direct selection

- Automatic routing uses explainable, deterministic initial rules tied to the canonical guide definitions.
- The user can select Tapio or a specific guide before sending a message.
- A message that mentions `@Tapio`, `@Ilmarinen`, `@Sampo`, `@Rauni`, or `@Otso` routes to that guide when automatic routing is selected.
- If no clear domain is present, Tapio remains active and asks or provides the next clarifying step.

##### Routing acceptance criteria

- [ ] Given a question about a residence-permit application, when automatic routing is used, then Ilmarinen is selected.
- [ ] Given a question about a rental agreement, when automatic routing is used, then Otso is selected.
- [ ] Given a user explicitly selects Rauni, when they send any message, then Rauni is selected instead of the automatic route.
- [ ] Given a user mentions `@Sampo`, when automatic routing is enabled, then Sampo is selected.
- [ ] Given a broad initial question, when no routing signal applies, then Tapio remains active.

#### Specialist scope and grounded responses

- Each specialist has a version-controlled system prompt that describes its scope and handoff boundary.
- The base Tapio prompt applies to every response and requires source-grounded, concise answers.
- The source panel renders retrieved documents and official URLs for each answer.

##### Grounded-response acceptance criteria

- [ ] Given a specialist route, when the response is generated, then the specialist's prompt is included with Tapio's base prompt.
- [ ] Given sources are retrieved, when the answer is rendered, then users can see the source title and URL in the source panel.
- [ ] Given no reliable document is retrieved, when a response is generated, then it does not fabricate a sourced answer.

### Nice-to-have (P1)

- Use a compact mobile presentation that collapses the guide directory and source panel without hiding them.
- Support localized guide labels and routing terms.
- Add per-answer feedback controls and attribute feedback to the active guide.
- Render a compact handoff event when Tapio delegates to another specialist.

### Future considerations (P2)

- Replace deterministic routing with a LangGraph coordinator that manages `TapioState`, tools, and handoff edges ([#12](https://github.com/Finntegrate/tapio/issues/12), [#13](https://github.com/Finntegrate/tapio/issues/13)).
- Persist conversations with a user-controlled title and deletion flow ([#16](https://github.com/Finntegrate/tapio/issues/16), [#35](https://github.com/Finntegrate/tapio/issues/35)).
- Introduce additional guides from the public roster only after each has a scope definition, official-source coverage, routing tests, and evaluation baseline.
- Add a guardrail classifier before routing and a structured human-support escalation flow ([#29](https://github.com/Finntegrate/tapio/issues/29)).

## Safety and privacy requirements

- Never present a guide as an official authority or professional representative.
- Prompts must instruct the model to acknowledge uncertainty and not invent sources.
- Responses involving permits, benefits, housing, or employment must retain a visible verification reminder.
- Production launch is blocked on the guardrail policy and tests in [#29](https://github.com/Finntegrate/tapio/issues/29), as well as grounding and citation work in [#28](https://github.com/Finntegrate/tapio/issues/28).
- Conversation persistence must not be enabled until data retention, deletion, and user consent are designed under the authentication and GDPR workstreams.

## Success metrics

No reliable baseline exists yet. Treat these as launch hypotheses and instrument them before judging the feature.

| Metric | Initial target | Measurement |
| --- | --- | --- |
| Guide identity visibility | 100% of assistant turns carry an agent identifier | UI event / rendered-message test |
| Explainable routing | 100% of automatically routed turns carry a route reason | Application event |
| Source availability | ≥90% of substantive answers display at least one official source when retrieval finds one | Groundedness evaluation and UI event |
| First-turn completion | ≥70% of pilot users receive a completed response without abandoning the chat | Session analytics, after instrumentation |
| User confidence | ≥70% of pilot feedback marks the response as helpful or clear | Per-answer feedback, after instrumentation |

The needed observability and product metrics are tracked in [#37](https://github.com/Finntegrate/tapio/issues/37) and [#39](https://github.com/Finntegrate/tapio/issues/39).

## Dependencies and phasing

| Phase | Scope | Dependencies |
| --- | --- | --- |
| **Initial implementation** | Canonical guide definitions, explainable routing, specialist prompts, shared conversation UI, source panel, and unit tests | Existing RAG pipeline |
| **Production safety** | Citation/groundedness enforcement and sensitive-query guardrails | #28, #29 |
| **Durable orchestration** | LangGraph router, retrieval tools, checkpointer, and saved conversations | #12–18, #35 |
| **Frontend graduation** | Mobile-first accessible client and API | #36, authentication/design decisions |

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Which multilingual languages and routing terms are included in the first public pilot? | Product and research | No — English prototype can proceed |
| What is the approved crisis/escalation resource list, and how is it maintained? | Safety, legal, and partnerships | Yes for broad release |
| What metrics/consent model are appropriate for pilot analytics? | Privacy and data | Yes before collecting usage data |
| ~~Which client replaces Gradio after the prototype is validated?~~ Resolved: SvelteKit (`app/`), see [ADR 0006](../ADRs/0006-retire-gradio.md). | Engineering and design | Resolved |
