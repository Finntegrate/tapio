# ADR 0011: A privacy and security baseline every component is held to

## Status

Proposed

## Date

2026-10-07

## Context

ADRs [0008](0008-auth-and-tenancy.md), [0009](0009-abuse-and-cost-controls.md), and [0010](0010-server-held-conversation-history.md) each apply minimisation, storage limitation, encryption, and defence in depth within their own scope. None says what conversations may be *used for*, how people are told what happens to their data, what they can ask for, how a breach is handled, or how far the language model is trusted. Those questions cut across every component.

GDPR Article 5 sets the principles any answer must meet, including accountability: the controller must be able to *demonstrate* compliance. Article 25 requires protection by design and by default. Two risks are specific to a language-model application: the model's input comes from users and crawled pages, so it is not a trusted component; and observability tooling, already a dependency, can quietly send every prompt to a third party.

## Decision

**Conversation content is used only to answer the person who wrote it.** Not to train models, build evaluation sets, run analytics, or for any other purpose, by Finntegrate or any processor. Model providers are used only on terms that forbid training on Tapio's prompts. Any other use needs its own ADR and lawful basis first.

**No observability tool sees conversation content or identifiers**, and this is enforced by the service, not left to configuration.

**People are told what happens to their data before they say anything**, in their language, with the full notice one step away.

**People can exercise their rights without being identified.** What a person can see, export, and delete is available in the interface, and Tapio does not identify anyone to answer a request (GDPR Art. 11).

**The language model gets the least privilege that lets it answer.** A turn can reach only the caller's own conversation and tools that cannot change anything or reach any store. User and retrieved content is treated as untrusted, and isolation rests on what the server allows, not on what the model is told. Model output never runs in the browser.

**Operators are few, strongly authenticated, and accountable**, with phishing-resistant multi-factor authentication and a reviewed record of every action. Proof of who did what is kept for operators only; for users it would contradict anonymity.

**Compliance is demonstrated, not asserted.** Every principle maps to the controls that meet it and the tests that verify them, every data item has a stated purpose and retention, privacy tests gate every merge, and a breach response plan exists before the beta opens.

## Consequences

### Positive

- One answer to "may we use conversations for X?": no, unless a later decision says otherwise.
- The likeliest accidental leak, enabling third-party tracing, cannot happen silently.
- A successful prompt injection can affect at most the attacker's own conversation.
- Compliance can be shown to an auditor, a partner, or the data protection authority.

### Negative

- Answer quality cannot be measured on real conversations; evaluation relies on synthetic and volunteered examples.
- Debugging without content in logs is harder.
- Strong authentication and audit records add friction for a small operator team.
- The mapping and register are evidence only while kept current.

### Risks

- A provider changing its terms could breach this decision without any change on Tapio's side.
- A new dependency can bring telemetry the known checks do not cover.
- Rendering output safely protects the browser, not the reader; misleading answers are a matter for grounding and guardrails.

## Alternatives considered

- **Restating principles in each ADR.** Rejected: partial copies, and cross-cutting questions still unanswered.
- **De-identified conversations for evaluation.** Rejected for now: free text from this population cannot be reliably de-identified.
- **Third-party tracing with redaction.** Rejected: redaction of free text is unreliable and fails open.
- **Non-repudiation for users.** Rejected: it requires identifying them.

## References

- [Specification: privacy and security baseline](../specs/privacy-and-security-baseline.md)
- [ADR 0008](0008-auth-and-tenancy.md), [ADR 0009](0009-abuse-and-cost-controls.md), [ADR 0010](0010-server-held-conversation-history.md)
- [PRD §5, §7.4–7.7](../PRD.md); GDPR Articles 5, 11, 15–21, 25, 30, and 33–35
- [#40](https://github.com/Finntegrate/tapio/issues/40), [#101](https://github.com/Finntegrate/tapio/issues/101), [#17](https://github.com/Finntegrate/tapio/issues/17)
