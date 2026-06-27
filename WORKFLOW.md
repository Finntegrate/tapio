# Project Workflow

This document explains how we organize and triage work in the Tapio project: the GitHub
Project board, our label taxonomy, and how issues move from idea to done.

## Table of Contents

- [Project Board](#project-board)
  - [Status](#status)
  - [Priority](#priority)
  - [Iteration](#iteration)
  - [Size](#size)
- [Issue Types](#issue-types)
- [Label Taxonomy](#label-taxonomy)
  - [Area Labels](#area-labels)
  - [Triage Labels](#triage-labels)
- [Triage Process](#triage-process)

## Project Board

All issues live on the [Finntegrate Team project board](https://github.com/orgs/Finntegrate/projects/1).
The board has several views (Board, Current iteration, Roadmap, My items) over the same
underlying set of fields:

### Status

- **Todo** — not yet started
- **In progress** — actively being worked on
- **Done** — completed (hidden from the default board view, which filters with `-status:Done`)

### Priority

- **High** — should be picked up first; usually foundational or blocking other work
- **Medium** — important, but not urgent
- **Low** — nice to have, or exploratory

Priority reflects project importance, not difficulty. A `good first issue` can still carry
a `High` priority label.

### Iteration

Some issues are assigned to a numbered iteration (e.g. `Iteration 2`) for sprint-style
planning. Most issues are not yet assigned to an iteration and simply sit in the backlog
until prioritized.

### Size

An optional t-shirt-size estimate (e.g. `M`) can be set on an issue once its scope is
understood. Most issues do not yet have a size set — add one if you have enough context
to estimate the work, but don't block on it.

## Issue Types

GitHub's built-in issue type field (`Bug`, `Feature`, `Task`) is available and used on some
issues (for example, #4 is typed `Task`), but adoption across the backlog is inconsistent —
many issues, including substantial engineering proposals, currently have no type set. If
you're triaging or filing an issue, setting a type when it's clear-cut (a defect is a `Bug`,
a net-new capability is a `Feature`, exploratory or maintenance work is a `Task`) is helpful,
but don't assume an unset type means anything in particular about an existing issue.

## Label Taxonomy

Labels fall into two categories: **area labels**, which describe what part of the system an
issue touches, and **triage labels**, which describe the issue's status or kind.

### Area Labels

| Label | Description |
| --- | --- |
| `agents` | Multi-agent / LangGraph |
| `auth` | Authentication and authorization |
| `dx` | Developer experience |
| `ops` | Observability, monitoring, alerting |
| `partners` | Partner integrations and visibility |
| `platform` | Infrastructure, deployment, hosting |
| `rag` | Retrieval pipeline |
| `safety` | AI safety, guardrails, response quality |
| `security` | Security and compliance |
| `ux` | User experience and interface |

An issue can carry more than one area label if it spans multiple parts of the system.

### Triage Labels

| Label | Description |
| --- | --- |
| `documentation` | Improvements or additions to documentation |
| `duplicate` | This issue or pull request already exists |
| `good first issue` | Good for newcomers |
| `help wanted` | Extra attention is needed |
| `invalid` | This doesn't seem right |
| `question` | Further information is requested |
| `wontfix` | This will not be worked on |

## Triage Process

When a new issue comes in:

1. A maintainer adds it to the [project board](https://github.com/orgs/Finntegrate/projects/1),
   which sets its initial **Status** to `Todo`.
2. The maintainer applies relevant **area label(s)** and a **Priority**.
3. If the issue looks approachable for new contributors, `good first issue` and/or
   `help wanted` are added.
4. Contributors can comment on an issue to claim it, then open a pull request that
   references the issue number once work begins, following the
   [Pull Request Process](CONTRIBUTING.md#pull-request-process) in `CONTRIBUTING.md`.
