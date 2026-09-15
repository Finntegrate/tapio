---
name: retro
description: Reflect on a pull request for Finntegrate/tapio — its diff, review comments, and commit history — to surface code smells, architectural rough patches, duplication, missing tests, deferred out-of-scope work, and unresolved review feedback, then turn the findings that survive a backlog dedupe check into properly labeled, prioritized, and sized issues. Use when the user wants a PR retrospective or "lessons learned," asks what follow-up work a PR left behind, wants to groom the backlog based on recently merged work, or mentions leftover TODOs, deferred scope, or review comments from a specific PR. Not for filing one already-scoped issue (see /create-issue) or browsing the existing backlog (see /backlog).
argument-hint: "[PR-number | branch-name]"
compatibility: Requires Claude Code with gh CLI installed and authenticated to Finntegrate/tapio, and jq (for reusing product-owner's project-board scripts).
---

You are running a PR retrospective for Finntegrate/tapio: read back over one pull request's actual changes and discussion, find the things it left behind, and turn the real ones into backlog issues with the fields they need to be pickup-ready.

$ARGUMENTS

If no argument is given, resolve the PR for the current branch. Otherwise treat the argument as a PR number (with or without a leading `#`) or a branch name.

This complements the project's other PM skills rather than overlapping them:

- `/create-issue` — file one already-scoped issue
- `/backlog` — browse and search the backlog read-only
- `/product-owner gaps` — find gaps between the PRD and the backlog (roadmap-driven, not PR-driven)

Use `/retro` specifically when the source of the finding is *this PR's own diff and discussion* — not the roadmap.

---

## Why this matters more than it looks

Every PR generates knowledge that's about to get lost: a shortcut taken because the "real" fix was out of scope, a reviewer comment that got a "good point, follow-up later" reply and then nothing, a test that got skipped because the fixture didn't exist yet. None of that is a bug in the code that just shipped — it's a gap in the backlog that only exists in someone's memory of doing the work. Left alone, it resurfaces months later as "wait, didn't we know about this?" The point of this skill is to convert that fresh, still-remembered context into issues immediately, while it's cheap to write down, rather than relying on anyone to remember it later.

Because it writes real issues and real project-board fields, treat it like `/create-issue`: show the full batch and get one explicit go-ahead before creating anything.

---

## Step 1 — Resolve the target PR

```bash
gh pr view $ARGUMENTS --repo Finntegrate/tapio --json number,title,url,state,body,baseRefName,headRefName,mergedAt
```

If `$ARGUMENTS` is empty, drop it from the command so `gh pr view` resolves the current branch's PR. State the resolved PR (number, title, state) before continuing — if it's still open and in-progress rather than merged, say so, since some findings (like "review comment unresolved") read differently on a live PR than a closed one.

If the PR body references issues it closes (`Closes #N`, `Fixes #N`), fetch those too — they establish what was explicitly in scope, which sharpens the difference between "a bug" and "a deliberate deferral."

---

## Step 2 — Gather the material

```bash
gh pr diff <number> --repo Finntegrate/tapio
gh pr view <number> --repo Finntegrate/tapio --json files,commits,comments,reviews
gh api repos/Finntegrate/tapio/pulls/<number>/comments --paginate
```

The last call gets inline review comments (tied to specific lines) that `gh pr view` doesn't surface — these are often the richest source of deferred work ("this works but should really use X", "not blocking, but...").

---

## Step 3 — Reflect across categories

Read the diff and discussion together, not in isolation — a comment often explains why a rough edge in the diff exists. For each thing you notice, sort it into one of:

- **Code smells / rough patches** — code that works but reads as a shortcut: duplicated logic, a function doing too much, a magic value that should be named or configured
- **Architectural issues** — a choice that's fine for this PR's scope but will strain as the surrounding system grows (check this against the LangGraph migration and provider-abstraction direction in `CLAUDE.md`)
- **Duplication** — logic this PR added that already exists elsewhere, or that a later PR is likely to re-add unless extracted now
- **Missing tests** — new behavior with no test, or a test that only covers the happy path
- **Deferred scope** — something explicitly called out as "not in this PR" in the description, commits, or comments
- **Unresolved review feedback** — a reviewer comment that wasn't addressed in code and didn't get an explicit "won't fix" resolution
- **Bugs noticed but not fixed** — edge cases the PR's own diff or discussion surfaces without resolving
- **Possible features / enhancements** — natural next steps the change makes obvious (a new capability now unlocked, a config knob worth exposing)

Skip anything the PR already fixed, anything that's a pure style nitpick a linter/formatter would catch, and anything so speculative you can't point to a specific line, file, or comment backing it. Every surviving finding should be traceable to something concrete — cite the file:line or the comment.

Also check this against durable project memory before finalizing findings — e.g. this project has no budget for persistent cloud databases and treats the RAG corpus as pointing to sources rather than being an authoritative KB, so a finding that quietly assumes otherwise (recommending Postgres, or treating crawl freshness as a correctness bug) is off-base here even if it would be reasonable advice generically.

---

## Step 4 — Backlog dedupe scan

This step is not optional, same as `/create-issue` Step 0. For each finding's theme (batch similar findings into one search rather than one search per finding):

```bash
gh issue list --repo Finntegrate/tapio --state all --search "KEYWORDS" \
  --json number,title,labels,state --limit 30
```

Search `--state all`, not just `open` — a finding might already be tracked in an issue that's since been closed as a duplicate, or reopened. Drop any finding that's already covered; note the rest as "related to #N" where relevant rather than dropping them outright.

---

## Step 5 — Present the batch and confirm

Show every surviving finding in one table before writing anything:

```text
# | Title | Type | Labels | Priority | Size | Related | Why (file/comment citation)
```

- **Type**: `Bug` / `Feature` / `Task`, per `/create-issue`'s taxonomy
- **Labels**: from the `CLAUDE.md` area taxonomy — pick all that genuinely apply
- **Priority**: `P0`/`P1`/`P2` — judge against actual urgency (a safety or security gap outranks a nice-to-have), not just "everything from this PR is P1"
- **Size**: `XS`/`S`/`M`/`L`/`XL`

Ask: "Look right? (y to create all / tell me which to drop or edit)". Let the user cut items — a retro table with ten items doesn't mean ten issues belong in the backlog.

---

## Step 6 — Create the issues

For each confirmed finding, write the body to a temp file under the scratchpad directory, then:

```bash
gh issue create --repo Finntegrate/tapio \
  --title "<title>" \
  --body-file "<path-to-temp-body-file>" \
  --label "<comma,separated,labels>"
```

Body follows `/create-issue` conventions (2-4 sentences + `**Checklist:**`), plus one line of provenance so a later reader knows where this came from:

```text
**Noticed in:** #<PR-number>'s review of `<file or area>`.
```

---

## Step 7 — Apply Priority and Size

Once every issue in the batch is created and has auto-added to the "Tapio" board, apply Priority and Size in one batch rather than one call per issue (see the rate-limit note in that script's header):

```bash
printf '<issue>\tPriority\t<P0|P1|P2>\n<issue>\tSize\t<XS|S|M|L|XL>\n...' \
  | .claude/skills/product-owner/scripts/bulk_set_project_fields.sh
```

Report back the created issue URLs with their applied Priority/Size.

---

## Conventions

- Never create anything without the Step 5 confirmation — this writes visible, shared state, same as `/create-issue`.
- Ground every finding in a specific diff line or comment; if you can't point to one, it's not a finding, it's a hunch — say so and leave it out rather than padding the batch.
- Priority and Size are project-board fields, not labels, per `CLAUDE.md` — never invent a new label to encode either.
- If the PR is small or clean, it's fine to come back with zero findings. Don't manufacture backlog items to justify having run the skill.
