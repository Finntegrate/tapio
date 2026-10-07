# ADR 0009: Gate the beta with partner access codes and bound what any request can cost

## Status

Accepted

## Date

2026-10-07

## Context

[ADR 0008](0008-auth-and-tenancy.md) puts a paid language model behind a public endpoint that needs no account. The abuse that matters most is *denial of wallet*: an attacker, a bug, or an agent loop spending money Finntegrate does not have. An unbounded bill is an outage by another name.

- **Per-user limits do not bound total cost**, because anonymous sessions are free to create.
- **Many actors at once is the real threat.** Only limits on the whole service hold against it.
- **Limiting concurrency does not limit rate.** A client controls how long its own turn lasts, and calls already in flight keep billing after it leaves.
- **The largest floods never reach the application.** Only the hosting layer can absorb them.
- **Legitimate users share addresses**, in reception centres, shelters, workshops, and on mobile networks, and the privacy posture rules out durable per-address records.
- **The beta reaches people through partners**, which gives a channel for admission that identifies no one.
- **Some people arrive in crisis**, and any control that refuses a turn can stand between them and emergency help.

## Decision

**The beta is gated by access codes distributed through partners.** A code admits without identifying. Codes are shared by a cohort, never issued per person, are infeasible to guess, and are never stored in readable form. Each code's sessions, turns, and share of capacity are bounded, so a leaked code can neither crowd out other partners nor spend more than its allowance, and a code can be stopped without costing its legitimate users their conversations.

**Total spend has a hard ceiling enforced outside our code**, by the model provider, so it holds even if our accounting is wrong. Finntegrate is alerted well before it is reached.

**Volumetric attacks are the hosting edge's to absorb.** No fingerprinting challenge is shown to visitors by default.

**Every request and every turn is bounded before it can cost anything**, at the worst case of a legitimate turn, so the bounds stop runaways without stopping real use. Every model call counts, wherever it is made.

**The maximum rate of spend is computable from configuration alone.** The service bounds how fast work may start, not only how much runs at once, and work holds its capacity until it has truly stopped. Contention is shared fairly across codes and shown to people as a short wait, not an error.

**Per-session and per-address limits are a generous backstop**, set so that shared networks are not collateral, using an address that is short-lived and non-identifying.

**No control hides emergency help.** Every message shown instead of an answer carries fixed emergency information that no model generates, and a turn already recognized as a crisis always delivers its resources.

**Paid tools are off, and the service has a kill switch** that closes it without a deploy.

**These controls are sufficient only while the beta's conditions hold**: admission by code, no paid tools, one process. Changing any of them requires further controls first, and the gate is reviewed on a fixed schedule rather than left in place indefinitely.

## Consequences

### Positive

- The worst case has a number, known before launch, and the total has a ceiling that does not depend on our code.
- A leaked code is bounded in spend and in share, and other partners keep being served.
- The beta needs no new service or paid infrastructure.
- Ordinary users notice nothing beyond entering a code.
- A person in crisis who meets any control still sees where to get help.

### Negative

- The beta is closed to anyone without a partner connection until the gate is lifted.
- Reaching the ceiling stops the service for everyone.
- The ceiling is itself a target: the design turns a financial attack into an availability attack, bounded per code, rather than removing it.
- Abandoned turns still cost money and capacity, within their bounds.
- Limits held in memory reset on restart and do not span processes.

### Risks

- Ceilings and rates set too low degrade real use; too high, they fail to protect. They need setting from measured cost and revisiting.
- A code shared publicly is noticed only through alerting.
- Prompt injection can try to spend on an attacker's behalf; bounds limit how much.
- Records of throttling and redemption must not become an identifying record.
- Bounds sized to today's orchestration must be revised when it changes, or legitimate turns, including crisis turns, will hit them.

## Alternatives considered

- **Per-session and per-address limits alone.** Rejected as sufficient: sessions are free and many actors defeat per-origin limits. Kept as a backstop.
- **A concurrency limit as the spend bound.** Rejected: it bounds spend only if turns have a minimum length, which clients control.
- **An in-application spend ceiling with degradation, now.** Deferred until the beta's conditions stop holding.
- **Proof-of-work on session creation, now.** Deferred: codes already bound session creation.
- **A third-party bot-detection challenge.** Rejected as a default: it discloses the visit and fingerprints. Allowed as an operator response to an attack.
- **One code per person.** Rejected: it becomes an identifier linking a person to a partner.
- **Locking a code after failed attempts.** Rejected: anyone could deny a partner its code.
- **Accounts for any use.** Rejected: reverses ADR 0008's default, and accounts are no harder to mass-create.

## References

- [Specification: abuse and cost controls](../specs/abuse-and-cost-controls.md)
- [ADR 0008](0008-auth-and-tenancy.md), [ADR 0010](0010-server-held-conversation-history.md), [ADR 0011](0011-privacy-and-security-baseline.md)
- [Guardrails](../specs/guardrails.md), [crisis and escalation resources](../specs/crisis-escalation-resources.md), [PRD §5](../PRD.md)
- [#32](https://github.com/Finntegrate/tapio/issues/32), [#17](https://github.com/Finntegrate/tapio/issues/17), [#16](https://github.com/Finntegrate/tapio/issues/16), [#44](https://github.com/Finntegrate/tapio/issues/44)
