# Abuse and cost controls — specification

**Status:** Proposed

**Owner:** Finntegrate

**Related architecture:** [ADR 0009](../ADRs/0009-abuse-and-cost-controls.md), [ADR 0008](../ADRs/0008-auth-and-tenancy.md)

## Problem statement

Anonymous access puts a paid language model and paid tools behind a public endpoint. The principal threat is denial of wallet, an unbounded bill that forces the service off. Related threats are session flooding, runaway agent loops and tool calls, prompt-injected spending, extraction of prompts, harassment, and use of the sign-in endpoint to email third parties. Controls must hold without identifying callers and must not penalize people who share a network address. The decision and its rationale are in [ADR 0009](../ADRs/0009-abuse-and-cost-controls.md); this document is the mechanism.

## Goals

1. Total spend over a period has a hard ceiling that no number of sessions can exceed.
2. A single turn's cost is bounded before it runs.
3. Controls are expressed in units of cost, so they mean the same thing for any request shape.
4. Ordinary users, including those behind shared addresses, are not the casualties.
5. Spend is visible and alerted on before the ceiling is reached.

## Non-goals

- **Billing or paid tiers.** These are cost controls, not monetization.
- **Identifying abusers.** Controls act on behaviour and spend, not identity, and keep no durable record of who was throttled.
- **Defeating a well-funded distributed attacker.** Only the ceiling holds against one; the rest is friction.
- **Content abuse policy.** Sensitive and off-topic queries are handled by [the guardrails policy](guardrails.md).

## Cost units

A *cost unit* is the metered spend of a turn: model input and output tokens priced by model, plus a fixed price per paid tool call. Prices come from configuration, so a model or provider change updates the unit without code changes.

Every limit and the global ceiling are expressed in cost units. The meter records actual spend from provider usage after each model and tool call, and a conservative estimate before a call is made. Enforcement uses the larger of the two when they disagree.

## Layers

Controls are applied in this order, cheapest first. A request rejected at a layer does not reach the next.

| # | Layer | Rejects | Costs a model call? |
| --- | --- | --- | --- |
| 1 | Global ceiling and degradation state | Anything the current state no longer serves | No |
| 2 | Edge limits | Floods by coarse network bucket | No |
| 3 | Session creation challenge | Mass creation of anonymous sessions | No |
| 4 | Per-principal budget | A principal past its budget | No |
| 5 | Turn bounds | Oversized or unbounded turns | No |
| 6 | Guardrail classification | Sensitive and off-topic content | Yes, metered |
| 7 | Generation and tools | | Yes, metered |

The guardrail classifier makes a model call ([guardrails policy](guardrails.md)), so it follows the free layers and is metered as spend.

## Global ceiling and degradation

The service has a budget in cost units per rolling day and per rolling month, set in configuration. Spend against each is tracked continuously.

The service moves through states as spend approaches the budget. Thresholds are configuration; the initial values are 70%, 90%, and 100%.

| State | Condition | Behaviour |
| --- | --- | --- |
| Normal | Below 70% | Full service for permitted principals |
| Conserving | 70–90% | Paid and metered tools off for everyone; anonymous per-principal budgets tightened; alert raised |
| Constrained | 90–100% | Cheaper model or retrieval-only answers; anonymous new sessions queued or declined; registered and partner principals keep their budgets |
| Closed | 100% | No generation. The interface states that the service is at capacity, when it is expected to resume, and links to the official sources the guides cite |

The state is stored where every request handler reads it, and a handler that cannot read it treats the state as Constrained, not Normal. State changes are logged with the spend that caused them and never with caller information.

Capacity is reserved so that one population cannot consume it all. A share of each budget, set in configuration, is held back for registered principals, and a partner organization's ceiling can only draw on its own allocation, so a leaked or abused referral link cannot starve everyone else, and anonymous traffic cannot starve registered users.

The Closed message is a fixed, translated string stored with the other user-facing strings, never generated.

## Per-principal budgets

Each principal has a budget in cost units per rolling window, in tiers set in configuration:

| Principal | Window | Relative budget |
| --- | --- | --- |
| Anonymous session | Rolling day | Smallest |
| Registered account | Rolling day | Larger |
| Partner organization | Rolling day, in aggregate | A ceiling on affiliated spend, drawn from its own allocation |

Budgets are charged as turns complete. An exhausted principal is told in plain language what happened and when its budget returns, and is pointed to official sources, which cost nothing to serve. The message never implies wrongdoing, and an organization ceiling that is reached does not blame the individual.

Anonymous budgets are intentionally ample for ordinary use. They exist so that one session cannot spend meaningfully, not to ration a person's help.

## Turn bounds

Applied before a turn runs and enforced during it.

| Bound | Effect |
| --- | --- |
| Maximum input length | Longer messages are rejected before any model call |
| Maximum output tokens | Passed to the provider on every call |
| Maximum history sent | Older turns are summarized or dropped, so cost does not grow with conversation length |
| Maximum graph steps | The orchestration graph aborts a turn that exceeds its step limit |
| Maximum tool calls per turn | Per tool and in total; further calls are refused |
| Maximum concurrent turns per principal | Extra concurrent requests wait or are rejected |
| Turn wall-clock timeout | The turn is cancelled and what was spent is still charged |

These bounds are what limit injected instructions and agent loops, since neither can exceed them however the model is steered.

## Tools

Tools carry a cost tier of free, metered, or paid, and an enabled flag ([#17](https://github.com/Finntegrate/tapio/issues/17)). Defaults:

- Free tools are available to every principal.
- Metered and paid tools are unavailable to anonymous principals unless an operator enables them for that tier.
- Any tool can be disabled in configuration without a deploy, and the Conserving state disables metered and paid tools automatically.
- Each invocation is metered at its configured price and logged with its tier and the cost, not the arguments.

## Session creation challenge

Creating an anonymous session requires solving a small proof-of-work challenge issued by the server. The browser solves it without user action. The difficulty is low in Normal state and rises with load and with the recent rate of session creation, so an attacker creating sessions in volume pays per session and ordinary use does not notice.

The challenge is self-hosted. No third party is told that a visitor is using Tapio. Difficulty is capped so that a low-end phone completes it within a few seconds, and there is a documented non-interactive path for assistive technology that does not depend on timing.

A third-party bot-detection service may be enabled by an operator as a response to an active attack. It is off by default, and enabling it is recorded and reviewed, because it sends visit information to that provider.

## Edge limits

A coarse network bucket is derived from a keyed hash of the address truncated to a coarse prefix, with a key that rotates daily. It is held in memory with a time-to-live of at most 24 hours, is never written to a log, an account, a conversation, or a partner report, and is never joined to any of them.

Edge limits are set high on purpose. They exist to blunt floods from a single origin, and they tolerate a reception centre or mobile carrier whose users share an address. The per-principal budget is the primary limit, and an edge limit alone never blocks a principal whose session is in good standing.

Limits apply separately to chat, session creation, and sign-in requests.

## Sign-in as a sending channel

The sign-in link endpoint can be used to send mail to people who did not ask for it.

- Limits apply per recipient address as well as per caller: a recipient receives no more than a small number of links per hour regardless of who asks.
- Requests are rate limited per network bucket, and require a solved session challenge.
- The response never reveals whether an address has an account.
- Mail contains the link and a plain line saying someone requested it, so an unwanted recipient can ignore it, and links expire in 15 minutes ([auth and tenancy](auth-and-tenancy.md)).
- Recipient counters hold only a keyed hash of the address and expire within an hour.

## Prompt extraction and misuse

Cost is bounded regardless of content, so this is a smaller concern. Two measures apply:

- System prompts are treated as non-secret and carry nothing that needs protecting; no credential, key, or partner configuration is ever placed in a prompt.
- Content the guardrail classifier refuses does not count against the budget more than the classification itself cost.

## Observability and alerting

Spend is attributed per turn by guide, model, and tool tier, with no caller identity, and exported to the same pipeline as the other operational metrics ([#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38)).

Alerts, to Finntegrate operators:

- Each state transition, with the spend that caused it
- Spend rate exceeding a multiple of the trailing baseline, before any threshold is reached
- Session creation rate or challenge difficulty at its cap
- A single turn reaching a hard bound
- Any single partner allocation above a configured share

Alerts carry aggregates and never message content or caller information.

Operator tools can force a state (for example, to Conserving ahead of a known spike), disable a tool, and adjust budgets, and record each action with the operator and the action.

## Failure modes

| Case | Behaviour |
| --- | --- |
| Spend meter unavailable | Treated as Constrained; no spend continues unmetered |
| Provider usage not returned for a call | Charged at the conservative pre-call estimate |
| State store unreadable | Treated as Constrained |
| Challenge service overloaded | Existing sessions unaffected; new sessions wait |
| Shared network at an edge limit | Principals in good standing continue; only session creation from that bucket is slowed |
| Budget exhausted mid-turn | The turn is stopped, what was spent is charged, and the interface says so plainly |

## Testing

- Ceiling: with simulated parallel session creation up to the challenge's capacity, total metered spend never exceeds the configured budget.
- Degradation: crossing each threshold changes the state, disables the tools it should, and produces the fixed Closed string at 100%.
- Fail-safe: with the meter or state store unavailable, handlers behave as Constrained.
- Turn bounds: an oversized message, a tool-call loop, and an unbounded graph are each stopped at their bound with the spend charged.
- Units: two requests of very different cost are charged differently, and a flood of cheap requests does not exhaust a budget meant for expensive ones.
- Reservation: anonymous traffic at its limit does not reduce registered principals' budgets, and one partner allocation cannot draw on another's.
- Privacy: no log line, metric, or alert contains an address, a bucket value, or an email address; a test asserts this against captured output.
- Sign-in: a recipient cannot be sent more than the hourly limit by any number of callers.
- Shared network: many principals in good standing behind one bucket are not blocked by the edge limit.

## Delivery

The budgets and ceiling are the first slice, because they are what make a public endpoint safe to open. [#32](https://github.com/Finntegrate/tapio/issues/32) owns the per-principal budgets and edge limits, [#17](https://github.com/Finntegrate/tapio/issues/17) the tool tiers, [#37](https://github.com/Finntegrate/tapio/issues/37) and [#38](https://github.com/Finntegrate/tapio/issues/38) the metering export and alerts, and [#44](https://github.com/Finntegrate/tapio/issues/44) the deployment settings. The service is not opened to anonymous public use before the global ceiling and turn bounds are in place.

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Monthly budget and the ceiling value for the pilot | Finntegrate | Yes, before public launch |
| Initial per-tier budgets, set against measured cost per typical conversation | Product and engineering | Yes, before public launch |
| Which proof-of-work scheme, and whether its battery cost on low-end phones is acceptable | Engineering | No |
| Whether a deployment-level protection in front of the service (a hosting provider's rate limiting) is acceptable for the privacy posture | Engineering, privacy | No |
| Whether Closed state should queue sessions rather than decline them | Product | No |
