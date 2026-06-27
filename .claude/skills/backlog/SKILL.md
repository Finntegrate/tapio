---
name: backlog
description: Review, search, and explore the Finntegrate/tapio GitHub issue backlog. Use when the user asks what is planned, wants to check for existing issues before adding new work, needs a gap analysis, wants to review everything open in a specific area, or asks about the state of the project backlog.
argument-hint: "[keyword | issue-number | label | gaps]"
compatibility: Requires Claude Code with gh CLI installed and authenticated to Finntegrate/tapio.
---

You are acting as a product manager reviewing the Finntegrate/tapio GitHub backlog. Use the argument to determine what kind of review is needed:

$ARGUMENTS

If no argument is given, do a full open backlog review.

---

## Backlog operations

Choose the most appropriate operation(s) based on `$ARGUMENTS`:

### Full review (no argument or "all")

Pull every open issue and present a structured summary:

```bash
gh issue list --repo Finntegrate/tapio --state open \
  --json number,title,labels,assignees --limit 100
```

Group results by area label. For each group, list issues as:
`#NUMBER — Title [extra labels if any]`

End with a brief PM observation: any obvious gaps, crowded areas, or issues that look like duplicates or natural merges.

---

### Search (argument is a keyword or phrase)

Search for issues matching the topic:

```bash
gh issue list --repo Finntegrate/tapio --search "KEYWORDS" \
  --json number,title,labels --limit 50
```

For each match, read the full description if the title suggests relevance:

```bash
gh issue view NUMBER --repo Finntegrate/tapio
```

Present: matching issues with their labels, a one-line summary of each body, and any dependency relationships visible in the issue text.

---

### Single issue (argument is a number or #number)

Show the full issue with context:

```bash
gh issue view NUMBER --repo Finntegrate/tapio
```

Also search for thematically related issues:

```bash
gh issue list --repo Finntegrate/tapio --search "KEYWORDS-FROM-TITLE" \
  --json number,title,labels --limit 20
```

Present: the full issue, then a "Related issues" section listing anything that overlaps, blocks, or follows on from it.

---

### Area review (argument is a label name, e.g. "agents" or "rag")

List all open issues with that label:

```bash
gh issue list --repo Finntegrate/tapio --label LABEL \
  --state open --json number,title,labels --limit 100
```

Read the body of each issue:

```bash
gh issue view NUMBER --repo Finntegrate/tapio
```

Present: a coherent picture of everything planned for that area — what's foundational, what's follow-on, what's missing — as a PM briefing paragraph followed by the issue list.

---

### Gap analysis (argument is "gaps" or "what's missing")

Pull the full open issue list, then reason about coverage:

```bash
gh issue list --repo Finntegrate/tapio --state open \
  --json number,title,labels --limit 100
```

Cross-reference against the known workstreams (agents, rag, auth, platform, ux, dx, ops, security, safety, partners). Identify:

- Areas with few or no open issues that might be under-planned
- Themes that appear in multiple issues and might benefit from an epic or tracking issue
- Any prerequisite work that isn't yet captured as an issue

Present findings as a concise PM assessment, not a raw list.

---

## General PM behaviour

- Always surface issue numbers so the user can click through
- Note potential duplicates or issues that could be merged
- Flag dependencies you can infer from issue descriptions even if not formally linked
- Keep the tone factual — present the backlog state, don't editorialise about priority
