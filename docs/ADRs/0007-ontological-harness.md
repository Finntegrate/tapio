# ADR 0007: Constrain guide answers with a deterministic harness

## Status

Proposed

## Date

2026-09-20

## Context

Tapio's guides answer in free prose. Retrieval grounds that prose and the shared system prompt asks for citations. Nothing in the pipeline checks what an answer committed to.

That is the problem in one sentence. An answer is a string. The things that can be wrong about it are not properties of strings. They are facts: this permit type does not exist, that office closed in January 2025, this authority does not handle this matter, that URL was not retrieved this turn, this guide is answering outside its remit.

### The failures, and what each one needs

Rather than adopt an architecture and look for problems it solves, start from the failures reachable in Tapio and ask what the cheapest sufficient check is for each.

| # | Failure | Example | Minimum check |
| --- | --- | --- | --- |
| 1 | Invented entity | A permit type that does not exist | Set membership |
| 2 | Superseded entity | Sending someone to a TE-toimisto, dissolved on 1 January 2025 with services moved to municipal employment areas | Date comparison |
| 3 | Real entity, impossible relation | Naming Kela as the authority for a residence permit | Typed relation lookup |
| 4 | Unretrieved citation | A plausible migri.fi URL that was not in this turn's retrieval set | Set membership |
| 5 | Out-of-remit answer | The housing guide answering a permit question | Set intersection |
| 6 | Terminology drift | One concept rendered three ways across Finnish, Swedish, and English ([#119](https://github.com/Finntegrate/tapio/issues/119)) | Label lookup |

Every one is set membership, a lookup, or a date comparison. The checks Tapio needs are decidable without inference, and that finding is what the rest of this decision rests on.

### Why better retrieval cannot close this

Failure 2 is the clearest case. Finnish administrative structure has been reorganized repeatedly and recently, and the corpus is crawled on a bounded schedule (PRD §5). A page naming a dissolved body is correctly retrieved and correctly summarized. No instruction causes a model to notice that an office closed.

The rates are mismatched. Administrative change lands on the day a law takes effect; corpus refresh lands on the crawl schedule. A curated record closes that gap because a supersession is one row, applied in hours.

### What proactive guidance does to the stakes

PRD §7.2 plans unrequested next steps. Answering a question badly and volunteering a wrong next step to someone working against a permit deadline are different risk classes. The second is not safely buildable on free generation.

### What the reference architecture is for

The neuro-symbolic harness in the source research — constrained decoding, a closed-world vocabulary gate, description-logic reasoning, a decoupled policy engine, signed evidence bundles — is built for agents that execute transactions and defend them under regulatory audit.

Tapio executes nothing and holds no case data. Its users include asylum seekers, undocumented people, and people fleeing abuse, for whom a per-turn signed record of what they asked is a safety hazard rather than a compliance asset (PRD §5). Some of that architecture transfers. Most of it answers questions Tapio does not have.

## Decision

Constrain guide answers with a deterministic harness, on the principles below.

**Mechanism is the specification's concern, not this record's.** How a phrase becomes an identifier, which checks run in what order, and what the register is authored and validated with are all expected to change as the work is built and measured. They live in the [ontological harness specification](../specs/ontological-harness.md), which is revised freely. This record fixes only what would require rethinking the approach to change.

**0. The harness is a safeguard, not the final say.** It removes a class of failure that is cheap to detect and expensive to leave in. It does not certify that an answer is right, and nothing downstream should be built as though it did. That bounds the engineering as much as the claims: each check earns its place by naming a failure it actually prevents, and the measure of success is whether guides answer better, not whether the harness is complete. Weight accrued here is weight taken from the rest of the PRD.

**1. Prose and commitments are separated.** The model writes the prose. A deterministic layer owns what a turn commits to: which concept, which authority, which next step, which source, which guide answered. Commitments are produced as a typed object before the prose, never parsed out of it afterwards.

**2. A versioned register is the authority, and it is closed-world.** An entity absent from the register cannot be asserted; absence is rejection, not silence. The register is append-only and time-indexed: entities are superseded rather than deleted, and carry the dates between which they were in force. Editions are dated and immutable, so an answer can name the edition it was produced against. Anchor to published Finnish vocabularies where they exist rather than minting identifiers by preference.

Append-only is not bookkeeping tidiness. It is what separates "what was true when this page was crawled" from "what is true now", which is the only honest way to reason over a corpus that is always somewhat stale.

**3. Interpretation is probabilistic, verification is deterministic.** Language is fuzzy — misspelled, inflected, colloquial, code-switched, half-finished — and nothing deterministic reads it well. So reading is a model's job, and what comes back is a structured classification the rest of the system can branch on, retry, and log. Verification of what that classification commits to is set membership, lookup, and date comparison, and it runs before the user sees anything.

Determinism belongs on the check, not on the reading. An interpreter reporting calibrated confidence in its own reading is an input to the decision rather than a violation of it; what is excluded is a second model asked to judge the first one's answer. A check that is itself uncertain is not a gate — it is a second opinion, and two opinions do not make a fact.

**4. Coherence and permission are separate.** Whether a plan is *coherent* — these entities exist, are in force, are related as claimed, were retrieved this turn, are within the answering guide's remit — is a different question from whether a coherent plan is *permitted* to be said now and unprompted. They change for different reasons and are maintained by different people. Folding permission into the domain model degrades the domain model.

**5. What could not be resolved is captured, not discarded.** A reference the harness cannot place is recorded, in the words the person actually used. That record is how the register's gaps become visible, and it is the difference between an artifact that is maintained and one that quietly rots. A register that only rejects degrades silently as the world moves; one that reports what it could not place tells its maintainers what to add next.

**6. Failure is bounded and honest.** One targeted repair attempt against the check that failed. A second failure degrades to the retrieved sources plus a plain statement that the answer could not be confirmed. Retry loops are not an acceptable failure mode, and a fabricated answer is never preferable to an admission.

**7. Guide scope is a set of register concepts**, not a hand-written keyword list, and a register-backed scope is a precondition for shipping a guide. This extends ADR 0005 and closes the representation drift tracked in [#154](https://github.com/Finntegrate/tapio/issues/154).

**8. The working picture is surfaced as correctable data.** The commitments behind an answer are already computed, so emitting them as typed, labelled data costs nothing extra and makes it possible to show a person what Tapio is assuming and let them correct it. It is presented as a correctable assumption, never as a stored record about anyone. Whether it reads as helpful or as a case file is a user-research question and is not settled here ([#33](https://github.com/Finntegrate/tapio/issues/33), [#36](https://github.com/Finntegrate/tapio/issues/36)).

**9. The register earns its scope.** It starts at the smallest set of concepts that lets one guide answer, and grows only where use shows the coverage is needed. Tapio is built by two part-time engineers and occasional contributors; a curated artifact that outgrows the attention available to maintain it fails in the way that matters most, by rejecting correct answers on the basis of stale curation.

**We do not adopt** description-logic reasoning, a decoupled policy engine, or signed evidence bundles. The first answers a question the failure table does not ask, since every check is decidable without inference. The second is machinery for a permission surface small enough to read. The third is directly contrary to PRD §5: a per-turn signed record binding a question to an asker is a hazard for people whose safety depends on no such record existing. Reproducibility is served instead by a content-addressed record of system state, carrying no user identifier, no query text, and no signature.

This work is assigned to milestone 2.1.0 and precedes further guide development.

## Consequences

### Positive

- Failures 1 through 5 become structurally impossible rather than statistically rare. A guide cannot assert an entity that does not exist, direct someone to a dissolved body, pair a matter with the wrong authority, cite a source it did not retrieve, or answer outside its remit without that being caught.
- Administrative change is corrected where it is tractable: a supersession is one row applied in hours, rather than a wait for recrawl and reindex.
- One artifact serves four planned pieces of work. The register's labels **are** the glossary of [#119](https://github.com/Finntegrate/tapio/issues/119); scope and routing under ADR 0005 and #154 need its concept sets; cross-language retrieval ([#26](https://github.com/Finntegrate/tapio/issues/26)) needs its labels; the evaluation set of [#27](https://github.com/Finntegrate/tapio/issues/27) needs stable identifiers to assert against.
- Proactive guidance becomes attemptable, because a suggestion is a traversal of asserted relations that cleared both questions in principle 4 rather than a generation.
- Unresolved references make coverage measurable, which turns "is the register good enough to enforce" into a decision with a number attached rather than a judgement call.
- The pipeline gains legible internal stages, which is what makes honest progress reporting and a correctable state display possible. Neither can be built on free prose.
- The register accumulates into a dated, machine-readable record of how the Finnish immigration system changes over time, which is useful beyond Tapio.

### Negative

- A curated artifact now exists and can rot. Principles 5 and 9 are mitigations, not guarantees.
- Latency rises, on a stack where latency is already unbenchmarked.
- Each new guide costs more up front: extend the register, declare scope in concepts, then ship.
- Ambiguity surfaces as a question. Some of those questions would have been answered correctly by a confident guess, and a guide that asks will sometimes read as less sure of itself than one that does not.

### Risks

- **Over-rejection.** A gate that blocks a correct answer because a concept was not registered yet is worse for that user than no gate. Every check therefore runs in shadow mode, logging without blocking, until coverage measurement shows it is safe to enforce. This is the failure mode closed-world designs actually die of.
- **The harness bounds form, not truth.** A well-formed, in-scope, correctly-cited answer can still misread its source. The harness must not be described, internally or to users, as making answers correct. This is the easiest claim to overstate and the most damaging one to overstate.
- **Resolution relocates hallucination rather than ending it.** Something still decides which phrase to take from the question. A confidently wrong reading that resolves cleanly passes every check. These checks catch invented entities, not misread ones.
- **Surfaced state may read as a case file**, which PRD §5 and §7.5 rule out. Mitigations exist in the specification, but perception is the hazard and perception is not fully controllable by design.
- **Anchoring may not pay off.** Of the first 129 concepts curated for Ilmarinen's domain, 7 carry an alignment to a published vocabulary. Finnish national vocabularies cover general terms well and administrative specifics thinly, so the register is likely to stay mostly hand-maintained, at roughly the cost that implies.

## Alternatives considered

### Improve prompting and retrieval instead

Rejected. Both reduce the frequency of these failures and neither makes them detectable. A stale entity in the corpus is correctly retrieved, and no instruction causes a model to notice that an office closed.

### Use a second language model to check the first

Rejected. It replaces an unverified answer with an unverified judgment, adds a full generation call, and produces no artifact anyone can inspect. The properties at issue are decidable by set membership and lookup, which do not need a model.

### Filter output heuristically after generation

Rejected. Regular expressions over prose cannot reliably separate a claim from a caveat, cannot bind a claim to its source, and fail silently in the languages Tapio must serve.

### Ship the glossary lookup of #119 alone

Rejected as insufficient, though it is a real improvement. A glossary that guides may consult drifts out of use. The same artifact used as a validation authority cannot, because every turn exercises it.

### Adopt the full reference architecture

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
- [Issue #154: Express guide scope as register concept sets](https://github.com/Finntegrate/tapio/issues/154)
