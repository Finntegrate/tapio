# Crisis and escalation resource list — governance

**Status:** Draft — initial candidate list populated, pending sign-off from a named safety/legal/partnerships owner

**Owner:** Safety, legal, and partnerships (PRD §11)

**Related:** [PRD §11, open questions](../PRD.md#11-open-questions), [PRD §7.4, safety boundary](../PRD.md#74-safety-boundary), [issue #102](https://github.com/Finntegrate/tapio/issues/102), [issue #29, guardrails for sensitive and off-topic queries](https://github.com/Finntegrate/tapio/issues/29), [`backend/app/config/crisis_resources.yaml`](../../backend/app/config/crisis_resources.yaml)

## Purpose

PRD §11 asks who approves Tapio's crisis/escalation resource list and how it stays current, and marks the question blocking for broad release. #29 implements the code path that surfaces these resources to users on a crisis-adjacent query (PRD §7.4), but that implementation needs real, approved data to consume rather than placeholder text. This document is the governance process underneath that list; it does not duplicate the data itself.

## Source of truth

The list lives in [`backend/app/config/crisis_resources.yaml`](../../backend/app/config/crisis_resources.yaml), not here and not hardcoded inline in guide prompts, so #29's implementation can load it directly. This document describes how that file is governed — who approves it and how it's kept current — not what's in it.

## Approval

- Every entry must be reviewed and approved by whoever holds safety/legal/partnerships responsibility for Tapio (PRD §11). Until a specific person or role is assigned that responsibility, the file's `status` stays `draft` and `approved_by` stays empty — #29 must not treat a draft list as authoritative for production traffic.
- Approval is recorded directly in the YAML file: `status` flips from `draft` to `approved`, and `approved_by` lists the name/role and date of whoever signed off.

## Review cadence

- The list is reviewed quarterly (`review_cadence: quarterly` in the YAML), or immediately if a contributor or partner organization reports a stale or incorrect contact.
- Every review updates `last_reviewed` and `next_review_due` in the YAML, even when no entry changes, so staleness is visible at a glance rather than requiring someone to check each URL by hand.
- A review confirms: phone numbers and URLs still resolve to the correct service, stated hours and languages are still accurate, and no new gap exists — e.g. a category of crisis Tapio now surfaces in conversation that isn't yet covered by an entry.

## Proposing a change

1. Open a PR editing `backend/app/config/crisis_resources.yaml` directly — not this document.
2. Cite a primary source (the organization's own site) for any new or changed contact detail; do not carry forward a number or URL from a secondary aggregator without checking it against the organization's own page.
3. Get sign-off from the current safety/legal/partnerships owner before merging.

## Consumption

Issue #29 is the only runtime consumer of this list. It must load `crisis_resources.yaml` directly and must not hardcode resource contact details inline in guide prompts (this was the specific failure mode PRD §11 flagged). Until #29 ships, the file has no runtime consumer — it exists so that implementation has real data to build against.

## Current gap

The initial pass of `crisis_resources.yaml` was populated from primary-source lookups (each organization's own site, checked 2026-09-16) so the format and data are ready to build against, but it has **not yet been reviewed or approved** by a named safety/legal/partnerships owner. Assigning that owner and getting explicit sign-off — which flips `status` to `approved` in the YAML — is the remaining step to close [PRD §11's open question](../PRD.md#11-open-questions) for this row.
