# ADR 0009: Gate the beta with partner access codes and bound what any request can cost

## Status

Proposed

## Date

2026-10-07

## Context

[ADR 0008](0008-auth-and-tenancy.md) makes anonymous use the default. That puts a paid language model behind a public endpoint that anyone can reach without an account. The abuse that matters most is not spam or scraping but *denial of wallet*: an attacker, a bug, or an agent loop spends the project's money. Finntegrate has no operating budget to absorb that, so an unbounded bill is an outage by another name. The service gets switched off and the people who needed it lose it.

Several facts shape the answer.

- **Per-user limits do not bound total cost.** Anonymous sessions are free to create, so any limit scoped to a session or an address can be multiplied by creating more of them.
- **Many actors at once is the real threat.** A coordinated burst from many origins defeats per-origin limits. What holds against it is a limit on the whole service: on how fast work can start, how much can run at once, and how much can be spent in total.
- **Limiting concurrency does not limit rate.** A client controls how long its own turn lasts, for example by disconnecting at once, and model calls already in flight keep billing after a client leaves. A spend bound has to rest on quantities the service sets, not ones it observes.
- **The largest floods never reach the application.** Volumetric attacks saturate the network before a request is parsed. Only the hosting layer can absorb them.
- **Legitimate users share addresses.** Reception centres, shelters, libraries, partner workshops, and mobile carriers put many real people behind one network address. A limit keyed mainly on address would lock out the people the service is for, and the privacy posture ([PRD §5](../PRD.md)) rules out durable per-address records.
- **The beta reaches people through partners.** Early users arrive by referral from organizations that work with them, which gives a distribution channel for admission that does not involve identifying anyone.
- **Some people arrive in crisis.** The guardrails exist so that a person describing an emergency is pointed to human help ([guardrails](../specs/guardrails.md)). Any control that refuses or cuts short a turn can also cut someone off from that.
- **The current API accepts conversation history from the client**, of any length. [ADR 0010](0010-server-held-conversation-history.md) moves history to the server.

The beta has to be safe to open without building infrastructure ahead of evidence, and without a normal user noticing any protection beyond entering a code.

## Decision

**The beta is gated by access codes distributed through partners.** A code admits a person to an anonymous session; it does not identify them. Codes are shared by many people, generated randomly with enough entropy that guessing is infeasible, and stored only in hashed form. Each code has its own limits on sessions, on turns per day, and on its share of the service's capacity, so a leaked code cannot crowd out other partners or spend more than its allowance. A code can stop admitting new sessions without ending the ones it admitted, and can end them too when it is being abused. Attempts at the entry form are limited by source, and a failed attempt reveals nothing about which codes exist.

**Total spend has a hard ceiling enforced outside our code.** The model provider's hard spend limit, or prepaid credit with automatic top-up off, is the ceiling, so it holds even if our own accounting is wrong. A provider that only alerts, or enforces with a lag, does not satisfy this. Finntegrate is alerted well before the ceiling is reached.

**Volumetric attacks are the hosting provider's to absorb.** The service runs behind the hosting provider's edge protection. The application does not try to survive floods it cannot see, and the edge does not put a fingerprinting challenge in front of visitors by default. The edge terminates TLS and so sees all traffic in plaintext, which makes choosing it a privacy decision as well.

**Every request is bounded before it can cost anything.** The size of a message, every component of the model's input, the length of the answer, the number of orchestration steps, model calls, and tool calls, and the time a turn may take are all capped. Every model call is counted where the model client is built, so no call site escapes the count. The bounds are set at the worst case of a legitimate turn, so they stop runaways without stopping real ones.

**The maximum rate of spend is computed from configuration alone.** A service-wide limit on how many turns may start per minute, together with the per-turn bounds, fixes the most the service can spend per hour, with no observed quantity in the calculation. A separate limit on how many turns run at once protects the provider's rate limits and response times. A turn holds its place until its last model call has finished, however the client behaves. Turns that cannot start yet wait briefly in a queue that is fair across codes, shown to the person as waiting rather than as an error.

**Per-session and per-address limits are a generous backstop.** They stop one session or one machine from monopolizing the service. The address-based limits are set high enough that a partner's workshop or a mobile carrier is not collateral, the address is taken only from the hosting edge, and it is held briefly and never in identifying form.

**No control hides emergency help.** Every message shown instead of an answer — the access-code page, a refused code, rate limits, the busy message, the closed state, and a turn stopped by a bound — carries a fixed, translated emergency line that no model generates. A turn already recognized as a crisis or legally sensitive always delivers its fixed resources, even if a bound fires.

**Paid tools are off, and the service has a kill switch.** No metered or paid tool is enabled during the beta. An operator can close the service, with a fixed closed message, without a deploy.

**These controls are sufficient only while the beta's conditions hold.** Opening admission without codes, enabling paid or metered tools, or running more than one process each require further controls first: an in-application spend ceiling with graceful degradation, cost-based metering, friction on mass session creation, and per-tier budgets. The gate is reviewed no later than six months after the beta opens, and is lifted only once the controls for open admission exist. The specification describes each stage and what triggers it.

## Consequences

### Positive

- The worst case has a number, computed before launch. The turn-start rate and per-turn bounds fix the maximum rate of spend, and the provider ceiling fixes the total.
- A leaked code is bounded in both spend and share of capacity, and other partners keep being served while it is dealt with.
- Almost everything is configuration or a small amount of code. No new service, store, or paid infrastructure is needed for the beta.
- The financial ceiling does not depend on our code being correct.
- Ordinary users notice nothing beyond entering a code: limits are set above normal use, and contention shows up as a short wait rather than a refusal.
- A person in crisis who hits any control still sees where to get emergency help.
- Access codes ride on the partner relationships the beta already depends on, and do not require anyone to be identified.

### Negative

- The beta is not open to everyone. A person without a partner connection cannot use it, which contradicts the anonymous-and-complete default of [ADR 0008](0008-auth-and-tenancy.md) until the gate is lifted.
- The provider ceiling is blunt. When it is reached the service stops, for everyone, until the next period or a top-up.
- The ceiling is itself a target. An attacker with a valid code can try to exhaust it and degrade the service for everyone. Per-code limits bound how much one code can contribute; the design turns a financial attack into an availability attack, it does not remove it.
- A turn whose client has gone keeps running and keeps its place until its model calls finish, so abandoned turns still cost money and capacity, within their bounds.
- In-memory limits reset when the process restarts, and do not work across processes.
- A code passed beyond its intended audience admits people the partner did not refer, until it is noticed.

### Risks

- A ceiling set too low switches the service off for legitimate use; too high, it fails to protect. It needs setting against measured cost per conversation and revisiting.
- Turn-start and concurrency limits set too tight turn a busy hour into a degraded experience for real users. They need sizing from observed load, and contention needs to be visible to operators.
- A code shared publicly, for example on social media, could admit many sessions quickly. Per-code limits bound how fast and how much; noticing it depends on alerting.
- Prompt injection can try to make the system spend on the attacker's behalf. Per-request bounds limit how much; they do not make the system immune to being steered.
- Records of throttling and code redemption are themselves data. The controls must not accumulate an identifying record of who was admitted or limited.
- The bounds are set at the worst case of today's graph. A change to the graph that adds model calls has to revise them, or legitimate turns, including crisis turns, start hitting them.

## Alternatives considered

### Per-session and per-address limits alone

Rejected as sufficient. New sessions are free and many actors at once defeat any per-origin limit. Retained as a backstop.

### A concurrency limit alone as the spend bound

Rejected. Concurrency bounds spend only if turns have a minimum duration, and a client sets its own turn's duration by disconnecting. A limit on how fast turns start bounds spend directly.

### An in-application spend ceiling with staged degradation, now

Deferred, not rejected. While access is gated and paid tools are off, the provider ceiling plus a computable maximum spend rate protects the budget with far less to build. It becomes required when those conditions stop holding.

### Proof-of-work or other friction on session creation, now

Deferred. Access codes already make mass session creation depend on a code that can be limited and revoked. Friction is the right tool when admission opens to everyone.

### A third-party bot-detection challenge on every visit

Rejected as a default. It tells a provider that this visitor is using an immigration assistant and often depends on fingerprinting, which conflicts with the privacy posture. An operator may enable it as a response to an active attack.

### One access code per person

Rejected. A personal code links a specific person to the partner that issued it, and becomes an identifier the system would then hold. A shared code admits without identifying, and its limits do the work a personal code would.

### Locking a code after failed attempts

Rejected. Anyone who knows a code exists could then deny it to its partner. Limiting the source of attempts protects capacity without handing out that power.

### Require an account for any use

Rejected. It reverses [ADR 0008](0008-auth-and-tenancy.md)'s protective default, and an email-only account is no harder to mass-create than a session.

## References

- [Specification: abuse and cost controls](../specs/abuse-and-cost-controls.md) — the mechanism this decision commits to
- [ADR 0008: Anonymous by default](0008-auth-and-tenancy.md) and its [specification](../specs/auth-and-tenancy.md)
- [ADR 0010: Server-held conversation history](0010-server-held-conversation-history.md)
- [ADR 0011: Privacy and security baseline](0011-privacy-and-security-baseline.md)
- [Guardrails](../specs/guardrails.md) and [crisis and escalation resources](../specs/crisis-escalation-resources.md)
- [PRD §5](../PRD.md)
- [#32: Usage quotas and rate limiting](https://github.com/Finntegrate/tapio/issues/32), [#17: Tool registry and cost guard](https://github.com/Finntegrate/tapio/issues/17), [#16: Checkpointer](https://github.com/Finntegrate/tapio/issues/16), [#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38), [#44: Production deployment](https://github.com/Finntegrate/tapio/issues/44)
