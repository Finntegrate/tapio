# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Tapio project.

An ADR captures a significant architectural decision made during the project: what was decided, why it was decided that way, and what the consequences are. ADRs are written at the time of the decision and remain in the repository as a permanent record — including decisions that are later superseded.

## Why ADRs?

- **Onboarding** — New contributors can understand not just what the architecture is, but why it is that way
- **Avoiding re-litigation** — Decisions that were already considered don't need to be re-argued from scratch
- **Accountability** — Trade-offs are made explicit rather than hidden in commit messages or tribal knowledge

## What belongs in an ADR

An ADR records a durable decision and the reasons for it. It should be short, and once accepted it should rarely need editing: an ADR changes when the decision changes, not when the implementation does.

Anything that would change as implementation proceeds belongs in a living document instead:

- **Specifications** (`docs/specs/`) hold the mechanism: flows, schemas, field names, algorithms, limits and their values, failure modes, and tests.
- **The PRD** (`docs/PRD.md`) holds what the product must do and for whom.
- **Tutorials, how-to guides, reference, and explanation** ([Diátaxis](https://diataxis.fr/)) hold everything a reader needs to learn, operate, or look up.

A useful test: if a change to the code would force a change to the ADR without the decision changing, that detail is in the wrong place. State a decision as a property ("deleting a conversation destroys its key") rather than as a mechanism ("keys are derived with HKDF-SHA-256"), and link to the specification for the rest.

## File naming

ADRs are numbered sequentially and given a short descriptive slug:

```text
NNNN-short-description.md
```

For example: `0001-cloudflare-crawler.md`

## Statuses

Each ADR carries one of the following statuses:

| Status                                     | Meaning                                                |
| ------------------------------------------ | ------------------------------------------------------ |
| **Proposed**                               | Under discussion, not yet adopted                      |
| **Accepted**                               | Decision has been adopted                              |
| **Deprecated**                             | No longer relevant but retained for historical context |
| **Superseded by [NNNN](NNNN-filename.md)** | Replaced by a later decision                           |

## Creating a new ADR

Copy `_template.md`, increment the number, fill in each section, and open a pull request for review.
