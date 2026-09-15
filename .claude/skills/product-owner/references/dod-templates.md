# Definition of Done templates

Base checklist by issue type, per the `create-issue` skill's `Bug` / `Feature` / `Task` taxonomy. Start from the matching template, then add the PRD-tied items below that apply to the issue's labels. Don't include a section that doesn't apply — a Task doesn't need "user-facing behavior verified," a docs-only change doesn't need a regression test.

## Feature

- [ ] Acceptance criteria in the issue body are all met
- [ ] Automated tests cover the new behavior (unit and/or integration, matching how the rest of the touched module is tested)
- [ ] No regression in existing tests or lint/type checks (`mise run` targets relevant to the touched package)
- [ ] User-facing behavior manually verified where applicable (UI change, new endpoint, new CLI command)
- [ ] Docs updated if the change affects setup, configuration, or a documented workflow

## Bug

- [ ] Root cause identified and stated in the PR/issue, not just the symptom patched
- [ ] Regression test added that fails before the fix and passes after
- [ ] Confirmed the fix doesn't reintroduce the issue under the original repro steps
- [ ] Related instances of the same root cause checked elsewhere in the codebase

## Task

- [ ] Deliverable stated in the issue is complete (research doc, refactor, config change, ops setup)
- [ ] No behavior regression where the task touches running code
- [ ] Follow-on work identified during the task is captured as new issues, not left implicit

## PRD-tied additions

Add these on top of the base template when the issue carries the matching label — they encode product principles from `docs/PRD.md` §5 that are easy to satisfy for the literal ask while quietly violating the product's actual constraints.

**`safety` label** (PRD §7.4 safety boundary):

- [ ] Change does not cause a guide to present itself as an official authority, legal representative, or caseworker
- [ ] Legal/medical/crisis-adjacent inputs are still recognized and redirected, not answered directly

**`security` label, or any feature touching accounts/storage** (PRD §5 no-PII posture, §7.5 privacy by design):

- [ ] No new identifying field (name, nationality, case number, contact detail) is collected, inferred, or persisted beyond what a user explicitly typed
- [ ] Any new persistent storage has a stated retention/deletion story

**`rag` label** (PRD §7.3 grounded answers):

- [ ] Answers built from this change still carry a citable official source, or the change explicitly doesn't affect answer generation
- [ ] A "no reliable source found" case is handled rather than silently producing an unsourced answer

**`agents` label** (PRD §6 guide network, §7.1 conversation):

- [ ] The guide's stated scope (per the roster in PRD §6) isn't widened or narrowed as a side effect
- [ ] If routing changes, a plain-language reason is still attached to the routed turn

**`partners` label** (PRD §7.7 partner visibility):

- [ ] Reporting surfaces aggregate signals only — no path to an individual end user's conversation without consent
