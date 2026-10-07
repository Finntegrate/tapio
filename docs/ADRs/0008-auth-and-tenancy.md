# ADR 0008: Anonymous by default, pseudonymous accounts, and partners as an opt-in reporting scope

## Status

Accepted

## Date

2026-10-07

## Context

Authentication, quotas, saved conversations, and partner reporting ([#31](https://github.com/Finntegrate/tapio/issues/31), [#32](https://github.com/Finntegrate/tapio/issues/32), [#35](https://github.com/Finntegrate/tapio/issues/35), [#16](https://github.com/Finntegrate/tapio/issues/16), [#45](https://github.com/Finntegrate/tapio/issues/45), [#46](https://github.com/Finntegrate/tapio/issues/46)) all depend on one question: who is a request from, and what may be remembered about them. Settled separately, they would answer it differently.

The PRD bounds the answer. Many users are asylum seekers, undocumented, or fleeing abuse, for whom a breach, a legal demand, or a compromised account can mean deportation or exposure to a persecutor (PRD §5). Access must never require proving identity or status (PRD §7.6). Partners see aggregate signals, never individuals (PRD §7.7). The threat model includes people close to the user: a controlling partner may share their device or read their inbox.

## Decision

**Anonymous use is the default and is complete.** Everything needed to get a sourced answer works without an account. During the beta, admission requires a partner access code ([ADR 0009](0009-abuse-and-cost-controls.md)), which admits without identifying.

**Accounts exist only to bring a conversation back, and hold no readable contact details.** An account is a pseudonymous identifier reached through control of an email inbox. The service keeps only what it needs to recognize the address again, never the address itself. Sign-in is passwordless and completes only in the browser that started it.

**No social login and no passwords.** A third-party identity provider would learn that the person uses an immigration assistant and link it to an identity they may be keeping separate. A password is a secret to store, breach, and reset.

**Three roles.** *Anonymous*, *registered*, and *partner administrator*. Partner administration is granted by Finntegrate, never self-asserted, and never includes reading anyone's conversation.

**A partner is a reporting and quota scope, not a tenant.** There is one corpus and one set of guides. A partner never owns, stores, or reads user data.

**Partner affiliation is opt-in and revocable.** A person is counted for a partner only if they choose to be, and can undo that choice. Partners see only aggregates, and any figure that could single out a person is withheld.

**Conversation ownership is enforced on every access.** Conversations are addressed by unguessable server-issued identifiers, and a caller who does not own one cannot tell it exists. Where conversations are stored and how they are protected is [ADR 0010](0010-server-held-conversation-history.md).

**Identity is kept apart from conversation storage**, so either can change engine without changing the other.

## Consequences

### Positive

- Someone who never creates an account leaves nothing that outlives a short expiry.
- A breach or legal demand against accounts yields no contact details.
- Sign-in cannot be completed from a forwarded message, so an abuser cannot sign a victim's browser into the abuser's account.
- Partners get the visibility the PRD promises without holding, or being compellable to produce, individual records.
- With no tenants, there is no per-tenant isolation to build or get wrong.

### Negative

- What the account keeps to recognize an address is still personal data, with controller obligations.
- The service cannot email anyone: no expiry warnings, no sign-in alerts, no recovery beyond signing in again.
- Whoever controls a person's inbox can sign in as them.
- Opt-in affiliation undercounts what partners refer.
- Refusing social login removes the lowest-friction path for those comfortable with it.
- The beta's access-code gate suspends "anonymous use is complete" until it is lifted.

### Risks

- Abuse controls tempt collecting network identifiers. Whatever [ADR 0009](0009-abuse-and-cost-controls.md) uses must be short-lived and non-identifying.
- Small partners produce small aggregates, and employers hold power over the people they refer. The withholding rules need review against real volumes.
- Lawful basis and controller obligations are decided in [#40](https://github.com/Finntegrate/tapio/issues/40) and [#101](https://github.com/Finntegrate/tapio/issues/101); this ADR must be revisited if they require collecting more.

## Alternatives considered

- **Accounts for everything.** Rejected: every first interaction becomes a disclosure, and that barrier is why this population would not use the service.
- **Social login.** Rejected for the third-party linkage above, despite being named in the original issue for its low friction.
- **Passwords.** Rejected: a breachable secret, and the reset flow needs email anyway.
- **Sign-in links.** Rejected: a link completes in whatever browser opens it, which enables account substitution by an abuser and is consumed by mail scanners.
- **Keeping the email address readable.** Rejected: its only uses would be messages that themselves disclose Tapio use to whoever reads the inbox.
- **Anonymous only.** Rejected: returning to a long permit process across devices is a stated need (PRD §7.6).
- **Partners as tenants, or partner membership lists.** Rejected: both create records of who a partner referred, which the privacy posture exists to avoid.
- **Network address as identity.** Rejected as a durable identifier; allowed only as a short-lived abuse signal.

## References

- [Specification: authentication and tenancy](../specs/auth-and-tenancy.md)
- [ADR 0009](0009-abuse-and-cost-controls.md), [ADR 0010](0010-server-held-conversation-history.md), [ADR 0011](0011-privacy-and-security-baseline.md), [ADR 0005](0005-multi-agent-chat-experience.md)
- [PRD §5, §7.5–7.7, §10, §11](../PRD.md)
- [#30: Design auth and tenancy model](https://github.com/Finntegrate/tapio/issues/30)
