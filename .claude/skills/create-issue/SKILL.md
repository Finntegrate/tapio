---
name: create-issue
description: Create a GitHub issue for Finntegrate/tapio from a free-form description. Always searches the open backlog for related or duplicate issues before drafting. Use when the user wants to file, add, or create a new issue, or when given a YAML planning file to batch-create issues from.
argument-hint: "[description] or [yaml-file]"
disable-model-invocation: true
compatibility: Requires Claude Code with gh CLI installed and authenticated to Finntegrate/tapio.
---

Create a well-formed GitHub issue for the Finntegrate/tapio project from the following description:

$ARGUMENTS

---

## Your job

Before drafting anything, scan the existing backlog for related issues. Then derive the issue fields, confirm with the user, and create via `gh`.

---

## Step 0 — Backlog scan

This step is not optional. Even if the request seems novel, check before drafting.

1. Pull the keyword(s) from the description and search:

   ```bash
   gh issue list --repo Finntegrate/tapio --search "KEYWORDS" \
     --json number,title,labels --limit 30
   ```

2. For any issue whose title overlaps with the request, read it:

   ```bash
   gh issue view NUMBER --repo Finntegrate/tapio
   ```

3. Report briefly:
   - **Related issues found**: list them with numbers and one-line summaries
   - **Duplicates**: if the request is already captured, say so and stop — ask the user if they want to update the existing issue instead
   - **Natural follow-ons**: note if the new issue would be blocked by, or block, something already open

If nothing relevant is found, say so and proceed.

---

## Step 1 — Derive issue fields

From the description (and informed by any related issues found above), determine:

- **Title**: concise, imperative, no internal ref prefixes
- **Type**: one of `Bug`, `Feature`, or `Task`
  - Bug — something broken that should work
  - Feature — new capability
  - Task — research, design, refactor, docs, or ops work with no user-visible output
- **Area labels**: one or more from the taxonomy below — pick all that genuinely apply
- **help wanted**: add if the issue would benefit from community contribution
- **good first issue**: add only if self-contained, well-scoped, requires no deep knowledge of the agent topology or RAG internals, and is XS–S effort
- **Body**: 2–4 sentences describing what and why, followed by a `**Checklist:**` of `- [ ]` items

If related issues were found in Step 0, note them in the body where relevant (e.g. "Depends on #12 which introduces the tool registry").

### Area label taxonomy

| Label | Scope |
|---|---|
| `rag` | Retrieval pipeline: crawling, parsing, chunking, embedding, ChromaDB |
| `agents` | Multi-agent system: LangGraph, orchestrator, specialist agents, tools |
| `auth` | Authentication, authorization, usage quotas |
| `platform` | Infrastructure, deployment, hosting, CI/CD |
| `ux` | User-facing interface and experience |
| `dx` | Developer experience: Codespaces, tooling, local setup |
| `ops` | Observability, monitoring, alerting, logging |
| `security` | Security, compliance, GDPR, secrets management |
| `safety` | AI safety: guardrails, grounding, off-topic handling |
| `partners` | Partner organisation management and reporting |
| `documentation` | Docs, READMEs, guides |

### good first issue criteria (all must apply)

- Scope is clearly bounded — one component or one file area
- Does not require understanding the LangGraph agent topology or RAG internals
- Has a clear definition of done
- Estimated effort XS or S

---

## Step 2 — Show and confirm

Present the derived fields in a compact block before doing anything:

```text
Title:   <title>
Type:    <Bug | Feature | Task>
Labels:  <comma-separated labels>
Related: <#N — title, or "none">
---
<issue body>
```

Ask: "Look right? (y to create / edit any field)"

If the user edits, update and confirm again before proceeding.

---

## Step 3 — Create the issue

Once confirmed, run:

```bash
gh issue create \
  --repo Finntegrate/tapio \
  --title "<title>" \
  --body "<body>" \
  --label "<comma,separated,labels>"
```

Print the returned issue URL.

---

## Step 4 — Batch mode (optional)

If `$ARGUMENTS` is a path to a `.yaml` file (e.g. `docs/planned-issues.yaml`), process each issue entry in sequence. For each entry, run the backlog scan for that issue's title/description, then confirm and create as above.

The YAML schema is at [references/issue-schema.yaml](references/issue-schema.yaml).

---

## Conventions

- Issue bodies use plain Markdown — no HTML, no internal planning refs
- Checklists use `- [ ]` format
- Titles are sentence-case, no trailing period
- Do not add `Priority` or `Effort` labels — those are project board fields set after creation
- Dependency relationships are set via GitHub's native "blocked by / blocking" sidebar, not labels
