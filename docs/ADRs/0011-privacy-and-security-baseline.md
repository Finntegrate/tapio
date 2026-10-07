# ADR 0011: A privacy and security baseline every component is held to

## Status

Proposed

## Date

2026-10-07

## Context

ADRs [0008](0008-auth-and-tenancy.md), [0009](0009-abuse-and-cost-controls.md), and [0010](0010-server-held-conversation-history.md) each decide part of how Tapio treats the people who use it: who they are to the system, what their use may cost, and where their conversations live. Each applies data minimisation, storage limitation, encryption, and defence in depth to its own scope. None of them says what conversations may be *used for*, how people are told what happens to their data, what they can ask for, how a breach is handled, or how far the language model itself is trusted. Those questions cut across every component, so answering them in one ADR's scope would leave the others silent.

GDPR Article 5 sets the principles the answers must satisfy: lawfulness, fairness, and transparency; purpose limitation; data minimisation; accuracy; storage limitation; integrity and confidentiality; and accountability, which requires the controller to be able to *demonstrate* the others. Article 25 requires data protection by design and by default. Common security practice adds least privilege, defence in depth, fail-safe and secure defaults, separation of duties, a small attack surface, and continuous testing.

Two risks are specific to a language-model application.

- **The model is not a trusted component.** Its input includes text from users and from crawled web pages, either of which can carry instructions written to steer it. Whatever the model can reach, an injected instruction can try to reach.
- **Observability tooling is a quiet exfiltration path.** LangChain's tracing client is already an installed dependency, and a single environment variable would send every prompt, conversation included, to a third party.

The users are people for whom a leak can mean deportation or exposure to a persecutor (PRD §5), so the baseline has to hold by construction, not by care.

## Decision

**Conversation content is used only to answer the person who wrote it.** It is not used to train or fine-tune models, to build evaluation sets, for analytics or product research, or for any other purpose, by Finntegrate or by any processor. Model providers are used only under terms that forbid training on Tapio's prompts. Any other use requires its own ADR and its own lawful basis before a single conversation is touched.

**No observability tool sees conversation content.** Logs, metrics, traces, and error reports carry no message content, email address, access code, or network address. Third-party tracing of model calls is disabled, and the service refuses to start if it is enabled.

**People are told what happens before they say anything.** Before the first message, a short notice in the person's language says what is kept, for how long, who processes it, and how to delete it, with the full privacy notice one step away.

**People can exercise their rights without being identified.** A registered person can see, export, and delete their conversations and delete their account. An anonymous person can see and delete their conversations and end their session. Tapio does not identify anyone in order to answer a request, and says so (GDPR Art. 11).

**The language model gets the least privilege that lets it answer.** A turn loads only the caller's own conversation. Tools are read-only and cannot reach the identity or conversation stores. Retrieved content and user messages are passed to the model as data, never as instructions. Model output is rendered as text, never as markup that can run in the browser.

**Operators are few, strongly authenticated, and accountable.** Access to production, its secrets, and the operator command requires phishing-resistant multi-factor authentication and a personal account. Every operator action is logged and the log is reviewed. Proof of who did what is kept for operators only; recording which person did what is a non-goal for users, because it would contradict anonymity.

**Compliance is demonstrated, not asserted.** A principles table maps each principle to the controls that meet it and the tests that verify them, and a purposes register lists every data item with its purpose, retention, and location. Together they are the basis of the record of processing activities and the impact assessment. A change that weakens a control updates the table in the same change. The privacy tests run in continuous integration and block a merge when they fail. There is a written breach response plan before the beta opens.

## Consequences

### Positive

- One place answers "may we use the conversations for X?", and the answer is no unless a later decision says otherwise.
- The most likely accidental leak, turning on tracing, cannot happen silently.
- A successful prompt injection can at most affect the attacker's own conversation, because nothing else is in reach of the model.
- An auditor, a partner, or the data protection authority can be shown how each principle is met and where it is tested.

### Negative

- Without conversation content, answer quality cannot be measured on real use. Evaluation has to rely on synthetic and volunteered examples.
- Debugging production problems without traces or content in logs is harder.
- Multi-factor authentication and an audit log add friction to a very small operator team.
- The principles table and purposes register are documents that must be kept current, or they stop being evidence of anything.

### Risks

- A provider whose terms change to allow training would breach this decision without any change on Tapio's side. Provider terms need reviewing when they change, not only when chosen.
- A new dependency can introduce its own telemetry. The startup check covers the known tracing clients, not every library that might phone home.
- Rendering as text protects the browser, not the reader. A model can still be steered into giving misleading text, which is a matter for grounding and guardrails, not this ADR.

## Alternatives considered

### Restate the principles in each ADR

Rejected. Each ADR would carry a partial copy, and a question that cuts across them, such as whether conversations can be used for evaluation, would still have no single answer.

### Allow de-identified conversations for evaluation

Rejected for now. Free text from this population cannot be reliably de-identified, because a person's situation can identify them as surely as their name. If evaluation on real use becomes necessary, it needs its own decision, lawful basis, and consent design.

### Third-party tracing with content redaction

Rejected. Redaction of free text is unreliable for the same reason, and a misconfigured redactor fails open. Tracing without content, kept in-house, gives most of the operational value.

### Non-repudiation for user actions

Rejected. Proving that a specific person did something requires identifying them, which is what the design avoids.

## References

- [Specification: privacy and security baseline](../specs/privacy-and-security-baseline.md), including the principles table
- [ADR 0008](0008-auth-and-tenancy.md), [ADR 0009](0009-abuse-and-cost-controls.md), [ADR 0010](0010-server-held-conversation-history.md)
- [PRD §5, §7.4–7.7](../PRD.md)
- GDPR Articles 5, 11, 15, 17, 20, 25, 30, 33, 34, and 35
- [#40: GDPR compliance review and data inventory](https://github.com/Finntegrate/tapio/issues/40), [#101: Consent model for usage analytics](https://github.com/Finntegrate/tapio/issues/101), [#17: Tool registry and cost guard](https://github.com/Finntegrate/tapio/issues/17), [#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38)
