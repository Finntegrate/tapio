# ADR 0009: Bound what anonymous access can cost with a spend ceiling, not only per-user limits

## Status

Proposed

## Date

2026-10-07

## Context

[ADR 0008](0008-auth-and-tenancy.md) makes anonymous use complete and the default. That leaves a public endpoint backed by a paid language model and, soon, paid tools ([#19](https://github.com/Finntegrate/tapio/issues/19)), reachable by anyone without an account. The abuse that follows is not mainly spam or scraping. It is *denial of wallet*: an attacker, or a bug, or an agent loop, spends the project's money. Finntegrate has no operating budget to absorb that (see [ADR 0008](0008-auth-and-tenancy.md)), so an unbounded bill is an outage by another name: the service gets switched off, and the people who needed it lose it.

Three facts shape the answer.

- **Per-user limits do not bound total cost.** Anonymous identities are free to create. Any limit scoped to a session, an account, or a network address can be multiplied by creating more of them, so the sum of all such limits is unbounded.
- **A request is not a unit of cost.** One short message and one that triggers a long answer, several retrievals, and a paid search differ by orders of magnitude. Counting requests protects neither the budget nor the user.
- **Legitimate users share addresses.** Reception centres, shelters, libraries, and mobile carriers put many real people behind one network address. A limit keyed mainly on address would lock out exactly the people the service is for, and the privacy posture ([PRD §5](../PRD.md)) rules out durable per-address records.

Abuse also has costs besides money: someone using the service to harass, to extract the model's instructions, or to make it emit harmful content; and the sign-in endpoint being used to send unwanted email to third parties.

## Decision

**Total spend is capped, absolutely, and the cap is the control that does not depend on identifying anyone.** The service has a budget for a period. When it is reached or approaching, the service degrades in a defined order rather than continuing to spend, and it does so the same way for every caller. Every other control exists to make that cap rarely reached and to share what it covers fairly; none of them replaces it.

**Cost is metered in units of cost, not requests.** Limits and the ceiling count what a turn actually spends (model usage and paid tool calls), so a limit means the same thing whichever way an attacker shapes a request.

**Each turn has a bounded cost before it starts.** Input size, output size, the number of steps and tool calls, and concurrency are limited per turn and per caller, so no single request, loop, or injected instruction can run away.

**Cheap checks run before expensive ones.** Anything that can reject a request without a model call does so first, and the checks themselves that call a model are metered like everything else.

**Paid capability is earned, not default.** Anonymous callers get the cheapest useful path. Metered and paid tools are unavailable to them unless an operator enables them, and they are individually disableable without a code change.

**Identity-based limits are per-principal budgets, with the network address only as a coarse, short-lived backstop.** The primary limit is on the session or account. A network signal exists to blunt mass session creation, is deliberately generous so shared addresses are not collateral, and never persists in identifying form.

**Creating anonymous sessions in volume costs the attacker something, and costs ordinary people nothing.** The mechanism is a lightweight proof of effort that adapts to load and does not require a third party to see who is visiting.

**Degradation is honest and keeps the highest-value path.** When capacity is constrained, the service says so plainly, keeps serving the cheapest path that still points people to official sources, and prefers to shed low-value usage over refusing everyone. Refusal never reads as an accusation.

**Spend is visible while it happens.** Cost is attributed and alerted on in time to act before the ceiling, not discovered afterwards on an invoice.

**Abuse of the sign-in email is bounded as abuse of a sending channel.** Email can be directed at third parties, so it is limited by recipient as well as by caller.

## Consequences

### Positive

- The worst case has a number. However many sessions are created, the project's exposure is the ceiling.
- The primary protection does not require knowing who a caller is, so it is compatible with the no-PII posture and with anonymous-by-default.
- Metering cost rather than requests means ordinary conversation is not throttled to defend against expensive requests, and a cheap flood does not exhaust a budget meant for costly ones.
- Shared-address users are not the primary casualty of the defence.

### Negative

- The ceiling is itself a denial-of-service lever. An attacker who cannot cost more than the ceiling can still reach it, degrading the service for everyone. The defence converts a financial attack into an availability attack; it does not remove it.
- Metering, budgeting, and degradation are real machinery to build and keep correct, ahead of any user-visible feature.
- Proof of effort adds friction and battery cost on low-end phones, which is common in this population.
- A degraded mode means some users get a thinner answer at the moment the service is under strain, which may be when it is most needed.

### Risks

- A ceiling set too low switches the service off for legitimate use; too high, it fails to protect. It needs setting against real pilot cost and revisiting.
- Cost estimates made before a turn can be wrong. The mechanism has to stay safe when they are, by also enforcing against actual spend.
- A determined, well-funded attacker with many real network origins defeats address-based and effort-based friction. Only the ceiling holds against them.
- Prompt injection can try to make the system spend on the attacker's behalf. Per-turn bounds limit this; they do not make the system immune to being steered.
- Retained records of who was throttled or challenged are themselves data. Controls must not accumulate an identifying record of abuse handling.

## Alternatives considered

### Per-user and per-address rate limits alone

Rejected as sufficient. Free identities multiply them, and per-address keying penalizes shared networks. Retained as layers, not as the defence.

### Require an account for any LLM use

Rejected. It reverses [ADR 0008](0008-auth-and-tenancy.md)'s protective default, and an email-only account is no more costly to mass-create than an anonymous session.

### A third-party bot-detection service on every visit

Rejected as the default. It tells a provider that this visitor is using an immigration assistant and often depends on fingerprinting, which conflicts with the privacy posture. Reconsidered only as an operator-enabled response to an active attack.

### Per-request counting

Rejected. A request is not a unit of cost; see Context.

### Run the model locally or self-hosted to remove marginal cost

Not a substitute. It changes the cost from per-token to capacity, which an attacker can still exhaust, and capacity has a budget too. It remains a valid way to lower the cost per turn within this decision.

### Do nothing until abuse appears

Rejected. The first incident would be the unbounded bill, and the cost of the mechanism is far lower than the cost of an outage during a pilot.

## References

- [Specification: abuse and cost controls](../specs/abuse-and-cost-controls.md) — the mechanism this decision commits to
- [ADR 0008: Anonymous by default](0008-auth-and-tenancy.md)
- [PRD §5](../PRD.md)
- [#32: Usage quotas and rate limiting](https://github.com/Finntegrate/tapio/issues/32), [#17: Tool registry and cost guard](https://github.com/Finntegrate/tapio/issues/17), [#19: Kagi Search tool](https://github.com/Finntegrate/tapio/issues/19), [#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38), [#44: Production deployment](https://github.com/Finntegrate/tapio/issues/44)
