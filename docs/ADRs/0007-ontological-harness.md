# ADR 0007: Constrain guide answers with an ontological harness

## Status

Proposed

## Date

2026-09-19

## Context

Tapio's guides answer in free prose. Retrieval grounds that prose and the shared system prompt asks for citations, but no part of the pipeline can check what an answer actually committed to. Whether a named permit type exists, whether an authority is the right one, whether a cited URL was in this turn's retrieval set, and whether the answering guide stayed inside its remit are all machine-checkable properties, and none of them are checked today.

Four consequences follow, each of which retrieval quality cannot fix on its own:

- **Stale entities.** Finnish administrative structure has been reorganized repeatedly and recently, and the crawled corpus is refreshed on a bounded schedule (PRD §5). Pages naming dissolved bodies remain in the corpus and remain relevant to retrieval.
- **Terminology drift.** Guides independently render the same concept across English, Finnish, and Swedish, which [#119](https://github.com/Finntegrate/tapio/issues/119) already identifies as a trust problem.
- **Unverifiable scope.** A guide's remit is a hand-written English sentence and a hand-maintained English keyword list. Nothing detects a guide answering outside it. ADR 0005 requires a documented scope and routing tests before any new guide ships, and seven more guides are planned.
- **Unattributable claims.** Sources are shown per turn, but no individual claim is bound to the chunk supporting it.

Proactive guidance (PRD §7.2) raises the stakes. Volunteering unrequested next steps to someone acting on a residence-permit deadline is a different risk class from answering a question badly, and the feature is unbuildable safely on free generation.

A separate body of work on deterministic harnesses for language-model agents offers a fuller apparatus: description-logic reasoning, decoupled policy engines, and cryptographically signed audit records. Most of that is designed for systems that execute transactions and must defend them under regulatory audit. Tapio executes nothing and holds no case data. One component, signed per-turn evidence binding a question to an answer, is actively contrary to PRD §5, which treats a data exposure for asylum seekers, undocumented people, and people fleeing abuse as a physical-safety risk.

This decision must be made now rather than after further guide development, because guide scope and routing are the parts it changes, and seven guides built on the current mechanism would each need retrofitting.

## Decision

We will constrain guide answers with a deterministic ontological harness, on the following principles. Implementation detail lives in the [ontological harness specification](../specs/ontological-harness.md), which is a living document; this record fixes the decision and is not updated as that specification evolves.

**1. Language and commitments are separated.** The model produces the prose. A deterministic layer owns the entity commitments a turn makes: which permit, which authority, which next step, which source, which guide answered. Commitments are emitted as typed slots in a structured plan, not as text to be parsed afterwards.

**2. A versioned term register is the authority, and it is closed-world.** An entity not present in the register cannot be asserted. Absence is rejection, not silence. The register anchors to published Finnish vocabularies where they exist rather than minting identifiers by preference.

**3. Validation is deterministic and runs before the response reaches the user.** Checks are set membership, shape constraints, and date comparison. No language model evaluates another language model's output, and no probabilistic self-check is treated as a gate.

**4. Failure is bounded and honest.** A failed check gets at most one targeted repair attempt. A second failure degrades to the retrieved sources plus a statement that the answer could not be confirmed. Retry loops are not an acceptable failure mode, and a fabricated answer is never preferable to an admission.

**5. The register is append-only and time-indexed.** Entities are superseded, never deleted, and carry the dates between which they were in force. The register is released as dated, immutable versions.

**6. Guide scope is expressed in register concepts.** A guide's remit becomes a set of concepts rather than a list of English keywords, and a register-backed scope becomes a precondition for shipping a guide, extending ADR 0005's requirement.

**7. Internal state that determines an answer is surfaced as data.** The working picture of the asker's situation that selects sources and next steps is emitted as a typed, labelled object carrying its own provenance, consumable by the interface, by assistive technology, and by other agents acting for a person. It is presented as a correctable assumption, never as a stored record about them.

**We will not adopt** description-logic reasoning, a decoupled policy engine, or signed evidence bundles. Reproducibility is served instead by a content-addressed provenance record describing system state, carrying no user identifier, no query text, and no signature.

This work is assigned to milestone 2.1.0 and precedes further guide development.

## Consequences

### Positive

- A class of failure becomes structurally impossible rather than statistically rare: a guide cannot assert an entity that does not exist, cite a source it did not retrieve, or answer outside its remit without that being detected.
- Administrative change is handled where it is tractable. A superseded entity is corrected by the register in days, rather than waiting for the corpus to be recrawled and reindexed.
- Several planned pieces of work converge on one artifact. The glossary of [#119](https://github.com/Finntegrate/tapio/issues/119), guide scope and routing tests under ADR 0005, cross-language retrieval in [#26](https://github.com/Finntegrate/tapio/issues/26), and the evaluation dataset of [#27](https://github.com/Finntegrate/tapio/issues/27) each need part of the register, and building it once serves all of them.
- Proactive guidance becomes safe to attempt, since a suggestion is a traversal of asserted relations rather than a generation.
- The pipeline gains legible internal stages, which makes both honest progress reporting and a user-correctable state display possible. Neither can be built on free prose generation.
- The register, kept append-only and dated, accumulates into a machine-readable record of how the Finnish immigration system changes over time, which is useful beyond Tapio.

### Negative

- A curated artifact now exists that can rot. Its value inverts if it is not maintained: an unmaintained register rejects correct answers.
- Per-turn latency increases on a stack where latency is already an unbenchmarked concern, and prose can no longer begin streaming until a plan has been validated.
- Three dependencies are added, and a schema-generation step enters the build.
- Each new guide costs more up front, because it must extend the register and declare its scope in concepts before it can ship.

### Risks

- **Over-rejection.** A gate that blocks a correct answer because a concept was not registered yet is worse for that user than no gate. Every gate therefore runs in shadow mode, logging without blocking, until measurement shows the register has adequate coverage.
- **The harness bounds form, not truth.** A well-formed, in-scope, correctly-cited answer can still misread its source. The harness must not be described, internally or to users, as making answers correct.
- **Surfacing internal state may increase misplaced trust rather than invite correction.** A structured panel of stated facts reads as a system that knows things. This is untested and belongs in user research ([#33](https://github.com/Finntegrate/tapio/issues/33), [#36](https://github.com/Finntegrate/tapio/issues/36)) before anything is built on top of it.
- **Surfaced state may read as a case file**, which is precisely what PRD §5 and §7.5 rule out. Mitigations exist in the specification, but perception is the hazard and perception is not fully controllable by design.
- **Small local models may handle structured output poorly**, which constrains how elaborate the plan schema can become and may not hold as the schema grows.

## Alternatives considered

### Improve prompting and retrieval instead

Rejected. Both reduce the frequency of these failures and neither makes them detectable. A stale entity in the corpus is correctly retrieved, and no instruction causes a model to notice that an office closed.

### Use a second language model to check the first

Rejected. It replaces an unverified answer with an unverified judgment, adds a full generation call, and provides no artifact anyone can inspect. The properties at issue are decidable by set membership and shape checks, which do not need a model.

### Filter output heuristically after generation

Rejected. Regular expressions over prose cannot reliably tell a claim from a caveat, cannot bind a claim to its source, and fail silently in the languages Tapio must serve.

### Ship the glossary lookup of #119 alone

Rejected as insufficient, though it is a genuine improvement. A glossary guides may consult drifts out of use. The same artifact used as a validation authority cannot.

### Adopt the full enterprise harness

Rejected. Description-logic reasoning, a policy engine, and signed evidence solve problems Tapio does not have, and the last conflicts directly with the no-PII posture. See the Decision section for what is taken and what is left.

### Defer until after the seven planned guides are built

Rejected. Guide scope and routing are what this decision changes, so deferral converts one piece of work into eight.

## References

- [Ontological harness specification](../specs/ontological-harness.md)
- [ADR 0005: Use one shared, guide-led conversation for Tapio's multi-agent experience](0005-multi-agent-chat-experience.md)
- [Product requirements document](../PRD.md), particularly §5, §6, §7.2, §7.3, and §7.5
- [Guardrails for sensitive and off-topic queries](../specs/guardrails.md)
- [Guide network grounding source research](../research/guide-network-grounding-sources.md)
- [Issue #26: Multi-language document retrieval](https://github.com/Finntegrate/tapio/issues/26)
- [Issue #27: Standing evaluation framework](https://github.com/Finntegrate/tapio/issues/27)
- [Issue #33: UX research on the guide/routing model](https://github.com/Finntegrate/tapio/issues/33)
- [Issue #119: Bilingual official-terminology glossary lookup](https://github.com/Finntegrate/tapio/issues/119)
