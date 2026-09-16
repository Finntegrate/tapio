# Tapio — product requirements document

**Status:** Living document

**Owner:** Finntegrate

**Scope:** The Tapio application — its frontend (`app/`) and backend (`backend/`) — as a product experienced by end users and partner organizations. It defines *what Tapio is for* and *what it must do*, not how it is built.

**Out of scope:** The `crawler/` and `ingest/` projects are independent pipelines that populate the shared content corpus Tapio reads from. They have their own roadmaps, operators, and documentation (see their respective READMEs) and are not covered here. This document treats "fresh, complete source content" as an input Tapio depends on, not a capability Tapio itself delivers.

**Related documents:** [ADR 0005 — multi-agent chat experience](ADRs/0005-multi-agent-chat-experience.md), [ADR 0006 — retire Gradio](ADRs/0006-retire-gradio.md), [Multi-agent chat spec](specs/multi-agent-chat.md), [Crisis and escalation resource list — governance](specs/crisis-escalation-resources.md).

## 1. Summary

Tapio is a guide network that helps people navigate Finnish immigration — residence permits, employment, benefits, and housing — through one coordinated conversation grounded in official sources. A user talks to Tapio, a coordinating guide who either answers directly or brings in a specialist (Ilmarinen, Sampo, Rauni, or Otso) for their area of expertise. Every substantive answer is traceable to an official source the user can go verify themselves.

Tapio is not a replacement for immigration authorities, legal counsel, or caseworkers. It is a first stop that helps people find the right information and the right next step faster than searching multiple government sites themselves.

A defining difference from searching official sites directly is that Tapio's guides are proactive: they anticipate common needs tied to a person's situation and surface relevant next steps, rather than waiting for a precisely-worded question. Many newcomers don't yet know what to ask, which authority to ask, or which keywords will surface the right official page — Tapio is designed to close that gap, not just answer it.

## 2. Problem statement

Finnish immigration information is spread across multiple official sites (Migri, Kela, TE-palvelut, municipal services, and others), written in dense administrative language, and often available primarily in Finnish and Swedish. People navigating this system — many of them non-native speakers under time pressure — struggle to find which information applies to their situation, in what order, and from which authority.

A single generic chatbot answer, with no visible expertise boundary and no source trail, does not solve this: it hides who is answering, why an answer applies to the user's situation, and whether the information can be trusted enough to act on. People making decisions about their residency status need to know an answer is grounded and verifiable, not just plausible.

## 3. Goals

1. Help a person get a focused, source-grounded answer to an immigration question without needing to know in advance which authority or topic area it falls under.
2. Anticipate what someone in a given situation is likely to need next, and surface it, rather than requiring the user to already know the right question to ask.
3. Make it visible which guide is answering and why, so users can calibrate trust and know when to seek official or human help instead.
4. Keep a person's whole journey — permits, employment, benefits, housing — in one continuous conversation, without making them repeat context when the topic shifts.
5. Always show the official source(s) behind a substantive answer, so users can verify before acting.
6. Support the partner organizations (NGOs, employers, municipalities) that refer people to Tapio, with visibility into how their referrals are using it.
7. Avoid collecting or retaining personally identifiable information, since a meaningful share of users are marginalized or at-risk (asylum seekers, undocumented people, people fleeing abuse) for whom a data exposure is not an inconvenience but a physical-safety risk.

## 4. Users

### Primary: people navigating Finnish immigration

- Students seeking study-related residence permits and enrollment information.
- Workers exploring employment-based permits, job seeking, and workplace rights.
- Families pursuing reunification, and people supporting a family member's application.
- Refugees and asylum seekers needing guidance on process and available support.

Shared needs: find accurate, applicable information quickly, in a language they're comfortable with, without having to cross-reference several government sites; rehearse or plan a conversation about a specific step (e.g. "what do I bring to my residence permit appointment?").

### Secondary: partner organizations

NGOs, employers, and municipal services that refer clients to Tapio and want to understand how it's being used to support their own advising work (see §8, Partner visibility).

## 5. Product principles

- **Proactive, not just reactive.** Immigrants often don't know what to ask, who to ask, or which keywords unlock a useful answer — that gap, not just answer accuracy, is what Tapio's guides exist to close. Guides should surface likely-relevant next steps and resources for a person's situation rather than waiting for a fully-formed question.
- **Tapio is a guide to official sources, not the authority itself.** The underlying content corpus is refreshed on a bounded schedule, not in real time. Every substantive response must foreground its sources and prompt verification for time-sensitive or high-stakes decisions rather than presenting itself as the definitive, up-to-the-minute record.
- **Expertise is visible, not implied.** A user should always be able to tell which guide answered and what that guide's remit is, so they can judge whether the answer is in-scope for their question.
- **Names are a way in, not a prerequisite.** A user shouldn't need to know the right keywords to reach the right guide — saying a guide's name should work as well as describing the problem. Guides referring to each other by name, in plain conversation, is how a user learns who else can help without having to study a directory first.
- **One journey, not one topic.** Immigration questions cross domains (a work permit question leads to a benefits question). The product keeps that journey in a single conversation rather than fragmenting it by topic.
- **Know the boundary.** Tapio is explicit about what it cannot do — give legal advice, make decisions on someone's behalf, or substitute for a caseworker — and hands off to official or human support when a question is beyond its remit.
- **General information, not a case service.** Tapio answers from publicly available official information. It is not a case tracker and does not hold, look up, or ask for an individual's case number, application status, or family details — that is a fundamentally different, more sensitive product than the one being built. What Tapio asks of a user mirrors what it's willing to hold: general questions in, general guidance out.
- **No PII by default.** This is Finntegrate's stated posture, not an aspiration: don't collect or store personally identifiable information beyond what a user explicitly volunteers in a conversation, and don't require it to get help. Many users are asylum seekers, undocumented people, or people fleeing abuse, for whom a data breach, subpoena, or account compromise can mean deportation, exposure to a persecutor, or worse — privacy failures here have no "minor incident" tier. Every feature that could accumulate identifying data (accounts, saved conversations, partner reporting, proactive guidance's use of situational context) must be designed around this constraint from the start, not patched to comply with it later.

## 6. The guide network

Each guide is named for a figure from Finnish cultural heritage, pairing that identity with a specific area of expertise — part of what makes the network legible and memorable rather than a single undifferentiated assistant. The public roster at [finntegrate.org/tapio](https://finntegrate.org/tapio/) is the canonical, user-facing definition of the full network; all product surfaces must agree with it. Status below reflects what's implemented today versus what the public site commits to but the product hasn't yet built.

| Guide | Role | In scope | Status |
| --- | --- | --- | --- |
| **Tapio** | Coordinator | Clarification, routing between guides, handoffs, cross-guide summaries | Live |
| **Ilmarinen** | The Craftsman of Documentation | Residence permits, visas, applications, official paperwork | Live |
| **Sampo** | The Prosperity Guide | Job seeking, networking, career pathways, workplace culture | Live |
| **Rauni** | The Prosperity Guardian | Kela, social security, benefits, family support | Live |
| **Otso** | The Housing Guardian | Housing, rental agreements, tenant rights, settlement | Live |
| **Pellervo** | The Harvest Guide | Entrepreneurship, business establishment, regulations | Planned |
| **Agricola** | The Language Mentor | Language learning, education, qualification recognition | Planned |
| **Louhi** | The Cultural Guide | Finnish customs, holidays, social norms, etiquette | Planned |
| **Mielikki** | The Healer | Healthcare navigation, medical services, insurance | Planned |
| **Lempi** | The Wellbeing Supporter | Mental health resources, community connections | Planned |
| **Ahti** | The Navigator | Transportation, utilities, banking, daily logistics | Planned |
| **Kokko** | The Regional Expert | Regional information, local resources, community guidance | Planned |

A user can let Tapio route automatically, pick a guide explicitly, or reach one by name mid-conversation. Each guide's own name is simply one of its activation terms, on the same footing as its topical keywords — saying "Ilmarinen" routes to Ilmarinen the same way saying "residence permit" does, whether written as plain text or a structured `@Name` mention. Full behavioral detail for the live roster lives in the [multi-agent chat spec](specs/multi-agent-chat.md)'s routing requirements, which predate the expanded public roster above and currently only specify the structured `@mention` form; they should be extended (scope, activation terms — including guide names — routing tests, per [ADR 0005](ADRs/0005-multi-agent-chat-experience.md)'s guidance that new guides need a documented scope before launch) as each planned guide is built, not assumed to already cover them.

## 7. Core functionality

### 7.1 Conversation

- One continuous, chronological conversation per session, presented like a channel — not separate rooms per guide.
- Every assistant message is attributed to the guide that produced it, with a plain-language reason when Tapio routes to a specialist.
- Users can ask a follow-up on a different topic without restating their situation; the relevant guide picks up the thread.
- A guide's name activates it exactly like any other routing keyword — a user who already knows (or overhears) a name doesn't need to also know the right topical phrasing to reach that guide.
- Guides refer to each other by name in plain conversation when handing off or pointing a user elsewhere (e.g. "Otso can help with the rental side of this"), so the roster is discoverable through use rather than something a user has to look up first.

### 7.2 Proactive guidance

- Guides suggest relevant next steps, related topics, and official resources tied to what a person has shared about their situation, instead of only answering the literal question asked.
- When a question implies unstated but common follow-on needs (e.g. a residence-permit question often comes with a registration or income-proof step), the responsible guide surfaces that connection rather than requiring the user to discover it themselves in a later turn.
- Handoffs between guides are themselves a form of proactive guidance: Tapio brings in a specialist because it anticipated the need, not only because the user asked for one by name.
- Proactive suggestions stay grounded in the same official sources as direct answers (§7.3) and stay within each guide's stated scope (§6) — anticipating a need is not license to guess or offer advice outside a guide's remit.

### 7.3 Grounded answers and sources

- Substantive answers cite the official source(s) they're drawn from, shown alongside the answer (title and URL).
- If no reliable source is found for a question, Tapio says so rather than producing an unsourced answer.
- Answers touching permits, benefits, housing, or employment carry a visible reminder to verify with the relevant official service before acting.

### 7.4 Safety boundary

- Tapio never presents a guide as an official authority, legal representative, or caseworker.
- Questions that are legal, medical, or crisis-adjacent are recognized and redirected to appropriate official or human support rather than answered as if Tapio were qualified to help directly. The resources redirected to come from the [approved crisis/escalation resource list](specs/crisis-escalation-resources.md) (see §11), not from an ad hoc list in a guide prompt. Recognition and redirection are implemented as a guardrail classifier that runs before routing; see the [guardrails policy](specs/guardrails.md) (#29).

### 7.5 Privacy by design

- Tapio does not ask for, store, or track a user's case number, application status, or family details; guides answer from publicly available official information, not from anything resembling an individual case file.
- The conversation gently and periodically reminds users not to share personal or identifying details they don't need to — a light, recurring nudge built into the interface, not a one-time disclaimer buried in terms of use.
- If a user volunteers sensitive personal information anyway, guides don't repeat it back unnecessarily, ask for more of it, or treat it as something to retain beyond answering the immediate question.

### 7.6 Access and continuity

- Returning users can pick up a prior conversation rather than starting over (depends on authentication and durable storage — see §9, Roadmap).
- Using Tapio, including returning to a saved conversation, never requires proving identity or immigration status; authentication is a low-friction, minimal-identity mechanism (e.g. magic link), not an identity-verification step.
- No PII is stored beyond what a user explicitly types into a conversation — the product does not infer, request, or persist identifying fields (name, nationality, case number, contact details) to enable this feature.
- Users can choose their preferred language for the conversation; guide answers and routing respect that choice where source language coverage allows.

### 7.7 Partner visibility

- Partner organizations that refer people to Tapio can see aggregate, privacy-respecting usage and outcome signals relevant to their own advising work (not individual users' conversations without consent).
- Partners can be organized and reported on as distinct entities from individual end users; partner-level reporting is built from aggregate counts, not from identifiable user records.

## 8. Non-goals

- **Replacing official authorities.** Tapio never issues decisions, submits applications, or acts as a legal or caseworker substitute.
- **Autonomous multi-agent debate.** Guides do not independently discuss a message among themselves; one guide answers per turn.
- **Unsolicited advice outside a guide's scope.** Being proactive means surfacing likely-relevant next steps grounded in official sources (§7.2); it does not mean guessing, speculating, or advising beyond a guide's stated remit to seem more helpful.
- **Permanent per-guide chat rooms.** The product is one shared journey, not a set of topic-siloed channels.
- **Being the source of truth.** Tapio points to official sources; it does not claim to be a more current or authoritative record than the sites it cites.
- **Collecting PII beyond what a conversation needs.** No identity verification, no required profile fields, no persistent tracking tied to a real identity — see §5's no-PII principle and #40.
- **Personal case tracking or private consultation.** Tapio does not look up, store, or reference an individual's application status, case number, or family details, and does not ask users for them. It is a general-information guide, not a case-management tool or private consultant (§7.5).
- **Building or operating the content pipeline.** How source content is discovered, crawled, and indexed is the concern of `crawler/` and `ingest/`, not this document.

## 9. Roadmap

Grouped by theme, referencing the current open backlog (`Finntegrate/tapio`, checked 2026-09-14). This is a shape of the roadmap, not a commitment to order — see the backlog for current prioritization.

| Theme | What it delivers | Backlog |
| --- | --- | --- |
| Complete the live guide network | Bring Sampo, Rauni, and Otso to the same RAG-binding, routing, and evaluation depth as Ilmarinen | [#15](https://github.com/Finntegrate/tapio/issues/15) |
| Expand the guide network | Design and build the 7 guides on the public roster (Pellervo, Agricola, Louhi, Mielikki, Lempi, Ahti, Kokko) not yet implemented — see §6. Scope and build order for all 7 are documented in the [planned guide network expansion spec](specs/planned-guide-network-expansion.md), grounded in [source research](research/guide-network-grounding-sources.md) | [#96](https://github.com/Finntegrate/tapio/issues/96), [#121](https://github.com/Finntegrate/tapio/issues/121) |
| Name-based routing | Treat each guide's own name as a routing keyword alongside its topical activation terms, and have guides use each other's names in handoffs (§7.1) | *(none — backlog gap; extends the routing work under [#15](https://github.com/Finntegrate/tapio/issues/15))* |
| Durable conversations | Persist conversations across sessions with contextual memory, user-controlled titling and deletion, with no PII stored beyond what a user explicitly types | [#16](https://github.com/Finntegrate/tapio/issues/16), [#35](https://github.com/Finntegrate/tapio/issues/35) |
| Accounts and access | Low-friction, minimal-identity authentication and a tenancy model that supports individual and partner-affiliated users without identity verification | [#30](https://github.com/Finntegrate/tapio/issues/30), [#31](https://github.com/Finntegrate/tapio/issues/31) |
| Safety guardrails | Classifier and escalation policy for sensitive or off-topic queries, ahead of broad release | [#29](https://github.com/Finntegrate/tapio/issues/29) |
| Answer quality | Deduplicate/rank sources, multi-language retrieval, a standing evaluation framework | [#68](https://github.com/Finntegrate/tapio/issues/68), [#26](https://github.com/Finntegrate/tapio/issues/26), [#27](https://github.com/Finntegrate/tapio/issues/27) |
| Language in the UI | Let users pick a conversation language in the chat interface | [#34](https://github.com/Finntegrate/tapio/issues/34) |
| Partner visibility | Partner org/reporting model and a partner-facing dashboard | [#45](https://github.com/Finntegrate/tapio/issues/45), [#46](https://github.com/Finntegrate/tapio/issues/46) |
| Trust and rate management | Usage quotas and rate limiting to keep the service usable and abuse-resistant | [#32](https://github.com/Finntegrate/tapio/issues/32) |
| Privacy and compliance | Formalize the no-PII posture as a written data inventory, GDPR checklist, and retention policy, given the sensitivity of immigration-status conversations | [#40](https://github.com/Finntegrate/tapio/issues/40) |
| In-conversation privacy nudge | Build the gentle, recurring reminder not to share unnecessary personal details (§7.5) into the chat interface | *(none — backlog gap)* |
| Operability | Structured logging/LLM observability, error tracking, usage metrics, so issues are caught before users report them | [#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38), [#39](https://github.com/Finntegrate/tapio/issues/39) |
| Production readiness | Deployment, secrets management, dependency/container scanning | [#41](https://github.com/Finntegrate/tapio/issues/41), [#42](https://github.com/Finntegrate/tapio/issues/42), [#44](https://github.com/Finntegrate/tapio/issues/44) |
| UX research | Validate what users actually need against the current guide/routing model | [#33](https://github.com/Finntegrate/tapio/issues/33), [#36](https://github.com/Finntegrate/tapio/issues/36) |
| Proactive guidance | Surface anticipated next steps and related resources per §7.2; no open issue yet defines this — a candidate for a new backlog item once scoped | *(none — backlog gap)* |

Before proposing new roadmap items, check this list and the live backlog (`gh issue list --repo Finntegrate/tapio --state open`) for overlap — see `CLAUDE.md`.

## 10. Success metrics

No usage baseline exists yet; treat these as launch hypotheses to instrument, not settled targets.

| Metric | Target | Why it matters |
| --- | --- | --- |
| Guide identity visibility | 100% of assistant turns carry a guide identifier | Users must always know who/what is answering |
| Explainable routing | 100% of auto-routed turns carry a stated reason | Trust depends on routing being legible, not opaque |
| Source availability | ≥90% of substantive answers show at least one official source when retrieval finds one | Grounding is the product's core trust mechanism |
| First-turn completion | ≥70% of new users receive a completed response without abandoning the chat | Signals the product is usable and responsive enough for a first-time visitor |
| User-reported confidence | ≥70% of rated responses marked helpful or clear | Direct signal on whether answers are actually useful |
| Safety boundary adherence | 0 responses that present a guide as an official/legal authority | A single violation undermines the trust the whole product depends on |
| Proactive suggestion uptake | ≥30% of proactive suggestions are followed (clicked, asked about, or acted on) | Confirms anticipated needs are actually relevant, not noise |
| No-PII posture | 0 identifying fields (name, nationality, case number, contact details) collected or required outside what a user volunteers in free text | For at-risk users, this is a safety property, not a compliance checkbox |

## 11. Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| What is the approved crisis/escalation resource list, and how is it kept current? Governance, cadence, and a draft list are defined in the [crisis/escalation resource spec](specs/crisis-escalation-resources.md); a named owner still needs to sign off before #29 can treat the list as authoritative. | Safety, legal, partnerships | Yes, for broad release — sign-off pending |
| What consent model applies to pilot usage analytics and partner-visible reporting? | Privacy and data | Yes, before collecting usage data |
| Which languages and locales does the first public pilot support? | Product and research | No — an English-first pilot can proceed |
| What does "partner-affiliated" mean for account/tenancy purposes, and how does it interact with individual accounts? | Product and engineering | Yes, before #30/#45 are designed |
| Proactive guidance (§7.2) has to anticipate needs from situational context (permit type, stage, location) without violating the no-PII principle (§5) — is within-conversation, non-persisted context sufficient, or does useful anticipation require something the no-PII posture rules out? | Product, privacy | Yes, before proactive guidance is implemented |
