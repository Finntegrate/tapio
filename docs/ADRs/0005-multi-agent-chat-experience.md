# ADR 0005: Use one shared, guide-led conversation for Tapio's multi-agent experience

## Status

Accepted

## Date

2026-08-02

## Context

Finntegrate's public Tapio page presents a coordinated network of specialized guides: Tapio, Ilmarinen, Sampo, Rauni, and Otso are the initial product scope. The current Gradio prototype represents all answers as one anonymous assistant, so a user cannot tell who is helping, why a specialist was selected, or what that guide is responsible for.

Immigration journeys often span permits, employment, benefits, and housing. Splitting that journey across permanent specialist chat rooms would require people to repeat context and makes handoffs invisible. Conversely, allowing every agent to reply to each message would be distracting and undermine trust.

The initial implementation must work with the current RAG pipeline while leaving a clear path to the LangGraph architecture planned in issues [#12](https://github.com/Finntegrate/tapio/issues/12), [#13](https://github.com/Finntegrate/tapio/issues/13), and [#16](https://github.com/Finntegrate/tapio/issues/16). It also needs to support grounding and sources ([#28](https://github.com/Finntegrate/tapio/issues/28)) and safety routing ([#29](https://github.com/Finntegrate/tapio/issues/29)).

## Decision

Tapio will use a single shared conversation, visually structured like a Slack channel, with Tapio acting as the visible guide and coordinator. A specialist is selected per user turn and replies in the same chronological conversation. The user can either let Tapio route automatically, select a guide, or mention one with `@Name`.

The initial guide roster is canonical and user-facing:

| Guide | Scope |
| --- | --- |
| Tapio | Clarification, routing, safe handoffs, and multi-guide summaries |
| Ilmarinen | Residence permits, visas, applications, and official documents |
| Sampo | Job seeking, networking, career pathways, and workplace culture |
| Rauni | Kela, social security, benefits, and family support |
| Otso | Housing, rental agreements, tenant rights, and settlement |

Each guide definition contains its scope, activation terms, responsibilities, out-of-scope boundary, presentation information, and an optional specialist system prompt. The public-site definition of Sampo as an employment and career guide is authoritative; the older internal wording that placed financial requirements under Sampo is superseded.

The first implementation uses deterministic, explainable routing. The interface shows the selected guide and the reason for the selection, and sends the selected specialist's prompt alongside Tapio's shared grounding and citation instructions. This is a user-experience seam, not the final orchestration implementation.

The eventual LangGraph state will replace the transient UI state with the following conceptual contract:

```python
class TapioState(TypedDict):
    messages: list[dict[str, str]]
    active_agent_id: str
    route_reason: str
    retrieved_documents: list[Document]
    locale: str
    thread_id: str
```

Tapio remains the entry and exit node. Specialist nodes may use retrieval tools, but they do not create separate user-visible conversations. Tapio will synthesize a final response when more than one specialist is needed.

## Consequences

### Positive

- Users retain one comprehensible record of their immigration journey.
- Agent expertise and handoffs are visible and explainable.
- The initial product can validate guide definitions and interaction patterns before introducing LangGraph persistence and tool orchestration.
- The agent-definition module is reusable by the future router, API, and non-Gradio front ends.
- Specialist prompts constrain each answer to a clear domain while retaining the existing official-source RAG flow.

### Negative

- Keyword routing is intentionally limited and can misclassify nuanced or multi-domain questions.
- Gradio provides a usable prototype but not the long-term mobile-first, accessible client identified in [#36](https://github.com/Finntegrate/tapio/issues/36).
- The transient chat history remains insufficient for users returning across sessions until checkpointing and authentication are implemented.

### Risks

- A specialist label can convey more confidence than the retrieved sources justify. Source presentation and groundedness checks remain mandatory.
- Users may have sensitive or crisis-adjacent needs that should bypass normal specialist routing; the guardrail classifier must precede the LangGraph router.
- The roster will expand. New guides must have a documented scope and routing test so that domains do not drift or overlap silently.

## Alternatives considered

### One permanent channel per guide

Rejected for the initial experience. It fragments a user's journey and requires repeated context-setting when a question crosses domains.

### A single anonymous assistant

Rejected because it hides specialism, routing decisions, and handoffs—the central value proposition of Tapio's guide network.

### All specialists reply to every message

Rejected because it produces unnecessary noise, makes accountability unclear, and increases cost and latency.

### Implement LangGraph before exposing guide identities

Rejected as an initial delivery approach. The guide model and interface can be tested safely with the existing grounded RAG pipeline while the persistent graph implementation is developed behind the same definitions.

## References

- [Tapio guide descriptions](https://finntegrate.org/tapio)
- [Issue #12: Design the Tapio agent architecture](https://github.com/Finntegrate/tapio/issues/12)
- [Issue #28: Response grounding and source citation](https://github.com/Finntegrate/tapio/issues/28)
- [Issue #29: Guardrails for sensitive and off-topic queries](https://github.com/Finntegrate/tapio/issues/29)
- [Issue #36: Evaluate and plan UI beyond Gradio](https://github.com/Finntegrate/tapio/issues/36)
