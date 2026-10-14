# Specifications

This directory contains the specifications for the Tapio project.

A specification describes how a part of Tapio works: flows, schemas, field names, algorithms, limits and their values, failure modes, and the tests that pin them down. Where an [ADR](../ADRs/README.md) records a decision and changes only when the decision changes, a specification is a living document — maintained against the implementation as the work proceeds.

## Statuses

Every specification carries exactly one status, on the `**Status:**` line directly under the title:

| Status       | When it applies                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Draft**    | Still being written or scoped. Not yet offered for review: parts may be missing, unsettled, or recorded as open questions.            |
| **Proposed** | Complete enough to review, awaiting a decision. The design is settled enough to critique; it has not been adopted.                   |
| **Accepted** | Adopted as the plan of record. Implementation may be partial or not started — what is agreed is what to build, not that it exists.   |
| **Implemented** | The mechanism the specification describes exists in the codebase. The specification is maintained against the implementation: when the code changes, the spec changes with it. |
| **Deprecated** | No longer the plan. Retained for context; the document that replaced it links back here, the way a superseded ADR does.           |

The statuses form a lifecycle — Draft → Proposed → Accepted → Implemented — so a reader can tell how current a specification is at a glance. A specification reaches Implemented when the mechanism it describes is in the codebase, not when the design is merely finished; landing the code is what moves it past Accepted.

## Who updates a specification's status

The specification's **Owner** updates the status as the work proceeds, and implementation pull requests are the main way that happens:

- An implementation PR that lands the mechanism a specification describes moves its status line to **Implemented** in the same PR. A spec whose code has shipped but whose status still reads Accepted is exactly the staleness this convention exists to prevent.
- A PR that changes the mechanism — a new limit, a renamed field, a different failure mode — updates the body of the specification to match in the same PR.
- Accepting a proposal moves its status from **Proposed** to **Accepted** when the decision is made, not when implementation starts.
- When the work that replaces a specification lands, it is marked **Deprecated** and its replacement links back to it.

Anyone reading a specification can correct a status that no longer matches reality — do it in the PR where you noticed it rather than leaving it for a follow-up.

## File naming

Specifications use a short descriptive kebab-case slug, one per topic:

```text
short-description.md
```

Unlike ADRs they are not numbered: a specification tracks a living feature and is updated in place, while an ADR remains an immutable record of a decision.
