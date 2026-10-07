# ADR 0009: Gate the beta with partner access codes and bound what any request can cost

## Status

Proposed

## Date

2026-10-07

## Context

[ADR 0008](0008-auth-and-tenancy.md) makes anonymous use the default. That puts a paid language model behind a public endpoint that anyone can reach without an account. The abuse that matters most is not spam or scraping but *denial of wallet*: an attacker, a bug, or an agent loop spends the project's money. Finntegrate has no operating budget to absorb that, so an unbounded bill is an outage by another name. The service gets switched off and the people who needed it lose it.

Several facts shape the answer.

- **Per-user limits do not bound total cost.** Anonymous sessions are free to create, so any limit scoped to a session or an address can be multiplied by creating more of them.
- **Many actors at once is the real threat.** A coordinated burst from many origins defeats per-origin limits. What holds against it is a limit on the whole service: on how much can run at once, and on how much can be spent in total.
- **The largest floods never reach the application.** Volumetric attacks saturate the network before a request is parsed. Only the hosting layer can absorb them.
- **Legitimate users share addresses.** Reception centres, shelters, libraries, and mobile carriers put many real people behind one network address. A limit keyed mainly on address would lock out the people the service is for, and the privacy posture ([PRD §5](../PRD.md)) rules out durable per-address records.
- **The beta reaches people through partners.** Early users arrive by referral from organizations that work with them, which gives a distribution channel for admission that does not involve identifying anyone.
- **The current API accepts conversation history from the client**, of any length. That is both an injection path and a way to make the project pay for invented input. [ADR 0008](0008-auth-and-tenancy.md) moves history to the server.

The beta has to be safe to open without building infrastructure ahead of evidence, and without a normal user noticing any of the protection.

## Decision

**The beta is gated by access codes distributed through partners.** A code admits a person to an anonymous session; it does not identify them. Codes are shared by many people, generated randomly with enough entropy that guessing is infeasible, stored only in hashed form, and individually revocable, expirable, and limited in how many sessions they can admit. Guessing is further bounded by limiting attempts at the entry form, and a failed attempt reveals nothing about which codes exist. A leaked code is contained by its own limits and revoked.

**Total spend has a hard ceiling enforced outside our code.** The model provider's spend limit or prepaid balance is the ceiling, so it holds even if our own accounting is wrong. Finntegrate is alerted well before it is reached. When it is reached, the service says plainly that it is at capacity and points to official sources, rather than failing with an error.

**Volumetric attacks are the hosting provider's to absorb.** The service runs behind the hosting provider's edge protection. The application does not try to survive floods it cannot see, and the edge does not put a fingerprinting challenge in front of visitors by default.

**Every request is bounded before it can cost anything.** The size of a message, the history sent to the model, the length of the answer, the number of orchestration steps and tool calls, and the time a turn may take are all capped. History comes only from the server ([ADR 0008](0008-auth-and-tenancy.md)), so its size is the server's decision.

**Model calls pass through a service-wide admission limit.** Only a bounded number of turns run at once, each session runs one at a time, and the rest wait their turn briefly in a fair queue. Waiting is shown to the person as waiting, not as an error, and a busy message appears only when the wait would be unreasonable. Together with the per-request bounds, this gives the service a maximum rate of spend that can be calculated in advance, which is what makes the ceiling safe: the alert arrives with time to act.

**Per-session and per-address limits are a generous backstop.** They stop one session or one machine from monopolizing the service. The address-based limit is set high enough that a shared network is not collateral, and the address is held only briefly and never in identifying form.

**Paid tools are off, and the service has a kill switch.** No metered or paid tool is enabled during the beta. An operator can close the service, with the same plain at-capacity message, without a deploy.

**These controls are sufficient only while the beta's conditions hold.** Opening admission without codes, enabling paid or metered tools, or running more than one process each require further controls first: an in-application spend ceiling with graceful degradation, cost-based metering, friction on mass session creation, and per-tier budgets. The specification describes those stages and what triggers each.

## Consequences

### Positive

- The worst case has a number. Admission control and per-request bounds fix the maximum rate of spend, and the provider ceiling fixes the total.
- Almost everything is configuration or a small amount of code. No new service, store, or paid infrastructure is needed for the beta.
- The financial ceiling does not depend on our code being correct.
- Ordinary users notice nothing: limits are set above normal use, and contention shows up as a short wait rather than a refusal.
- Access codes ride on the partner relationships the beta already depends on, and do not require anyone to be identified.
- Server-held history closes the cheapest attack available against the current API.

### Negative

- The beta is not open to everyone. A person without a partner connection cannot use it, which contradicts the anonymous-and-complete default of [ADR 0008](0008-auth-and-tenancy.md) for the duration of the beta.
- The provider ceiling is blunt. When it is reached the service stops, for everyone, until the next period or a top-up.
- The ceiling is itself a target. An attacker with a valid code can try to exhaust it and degrade the service for everyone. The design turns a financial attack into an availability attack, bounded by the code's limits; it does not remove it.
- In-memory limits reset when the process restarts, and do not work across processes.
- A code passed beyond its intended audience admits people the partner did not refer, until it is noticed and revoked.

### Risks

- A ceiling set too low switches the service off for legitimate use; too high, it fails to protect. It needs setting against measured cost per conversation and revisiting.
- Admission and queue limits set too tight turn a busy hour into a degraded experience for real users. They need sizing from observed load, and contention needs to be visible to operators.
- A code shared publicly, for example on social media, could admit many sessions quickly. Per-code admission limits bound how fast; noticing it depends on alerting.
- Prompt injection can try to make the system spend on the attacker's behalf. Per-request bounds limit how much; they do not make the system immune to being steered.
- Records of throttling and code redemption are themselves data. The controls must not accumulate an identifying record of who was admitted or limited.

## Alternatives considered

### Per-session and per-address limits alone

Rejected as sufficient. New sessions are free and many actors at once defeat any per-origin limit. Retained as a backstop.

### An in-application spend ceiling with staged degradation, now

Deferred, not rejected. While access is gated and paid tools are off, the provider ceiling plus a computable maximum spend rate protects the budget with far less to build. It becomes required when those conditions stop holding.

### Proof-of-work or other friction on session creation, now

Deferred. Access codes already make mass session creation depend on a code that can be limited and revoked. Friction is the right tool when admission opens to everyone.

### A third-party bot-detection challenge on every visit

Rejected as a default. It tells a provider that this visitor is using an immigration assistant and often depends on fingerprinting, which conflicts with the privacy posture. An operator may enable it as a response to an active attack.

### One access code per person

Rejected. A personal code links a specific person to the partner that issued it, and becomes an identifier the system would then hold. A shared code admits without identifying, and its limits do the work a personal code would.

### Require an account for any use

Rejected. It reverses [ADR 0008](0008-auth-and-tenancy.md)'s protective default, and an email-only account is no harder to mass-create than a session.

### Keep conversation history on the client

Rejected. A client that supplies history can forge earlier turns to steer the model and can inflate the input the project pays for.

## References

- [Specification: abuse and cost controls](../specs/abuse-and-cost-controls.md) — the mechanism this decision commits to
- [ADR 0008: Anonymous by default](0008-auth-and-tenancy.md) and its [specification](../specs/auth-and-tenancy.md)
- [PRD §5](../PRD.md)
- [#32: Usage quotas and rate limiting](https://github.com/Finntegrate/tapio/issues/32), [#17: Tool registry and cost guard](https://github.com/Finntegrate/tapio/issues/17), [#16: Checkpointer](https://github.com/Finntegrate/tapio/issues/16), [#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38), [#44: Production deployment](https://github.com/Finntegrate/tapio/issues/44)
