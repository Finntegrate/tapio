# Tapio — Claude Project Context

Tapio is an AI-powered Finnish immigration assistant built by the Finntegrate project. It answers questions about Finnish immigration processes using a RAG pipeline over official sources, and is moving toward a LangGraph multi-agent architecture.

## Current stack

- **LLM runtime**: Ollama (local), migrating to a configurable provider abstraction
- **Embeddings**: `all-MiniLM-L6-v2`
- **Vector store**: ChromaDB
- **Orchestration**: LangChain → LangGraph (in progress)
- **UI**: Gradio (being evaluated for replacement)
- **Task runner**: mise (`mise.toml` at project root)
- **Package manager**: uv
- **CI target**: GitHub Actions + Codespaces

## Agents (planned)

| Name      | Role                                               |
| --------- | -------------------------------------------------- |
| Tapio     | Orchestrator — routes queries, synthesises answers |
| Ilmarinen | Immigration documents and forms                    |
| Sampo     | Financial requirements and costs                   |
| Rauni     | Work permits and employment                        |
| Otso      | Settlement and daily life                          |

## Backlog awareness

**Always check the GitHub backlog before planning, drafting, or creating issues.**

When a user asks to plan work, brainstorm features, or create a new issue:

1. Pull the full open issue list:

   ```bash
   gh issue list --repo Finntegrate/tapio --state open \
     --json number,title,labels --limit 100
   ```

2. Search for issues related to the topic being discussed:

   ```bash
   gh issue list --repo Finntegrate/tapio --search "KEYWORDS" \
     --json number,title,labels
   ```

3. For any issue whose title looks related, read its full description:

   ```bash
   gh issue view NUMBER --repo Finntegrate/tapio
   ```

4. Surface relevant existing issues to the user before proposing new ones. Note potential duplicates, natural follow-ons, or dependencies.

The goal is to behave like a product manager who has read every open issue: aware of what's already planned, able to spot overlaps, and able to suggest how new work fits into (or consolidates) the existing backlog.

## Label taxonomy

| Label           | Scope                                   |
| --------------- | --------------------------------------- |
| `rag`           | Retrieval pipeline                      |
| `agents`        | Multi-agent / LangGraph                 |
| `auth`          | Authentication and authorization        |
| `platform`      | Infrastructure, deployment, hosting     |
| `ux`            | User experience and interface           |
| `dx`            | Developer experience                    |
| `ops`           | Observability, monitoring, alerting     |
| `security`      | Security and compliance                 |
| `safety`        | AI safety, guardrails, response quality |
| `partners`      | Partner integrations and visibility     |
| `documentation` | Docs, READMEs, guides                   |

## Project commands

Skills in `.claude/skills/` are automatically available as slash commands when this repo is open in Claude Code — no manual setup required. If commands don't appear after opening the project, restart Claude Code once so it can watch the new directory.

| Command | Purpose |
| --- | --- |
| `/create-issue <description or yaml path>` | Create a single issue (or batch from YAML) after a backlog scan |
| `/backlog [keyword / number / label / gaps]` | Explore and review the open backlog |

## Key files

| Path                                      | Purpose                                                  |
| ----------------------------------------- | -------------------------------------------------------- |
| `.claude/skills/create-issue/references/issue-schema.yaml` | YAML schema for drafting batches of issues |
| `.claude/skills/create-issue/SKILL.md`    | Source for `/create-issue`                               |
| `.claude/skills/backlog/SKILL.md`         | Source for `/backlog`                                    |
| `mise.toml`                               | Task runner targets (`mise run <task>`)                  |

## Conventions

- Issue titles: sentence-case, imperative, no trailing period, no internal ref prefixes
- No `Priority` or `Effort` labels — set those as project fields on the board
- Dependency relationships via GitHub's native "blocked by / blocking" sidebar feature
- All work targets the `Finntegrate/tapio` repo and auto-adds to the Finntegrate Team project board
