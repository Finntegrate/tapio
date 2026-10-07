# ADR 0008: Anonymous by default, pseudonymous accounts, and partners as an opt-in reporting scope

## Status

Proposed

## Date

2026-10-07

## Context

Authentication, usage quotas, saved conversations, and partner reporting all need an answer to the same question: who is a request from, and what may be remembered about them. Issues [#31](https://github.com/Finntegrate/tapio/issues/31) (authentication), [#32](https://github.com/Finntegrate/tapio/issues/32) (quotas), [#35](https://github.com/Finntegrate/tapio/issues/35) (saved conversations), [#16](https://github.com/Finntegrate/tapio/issues/16) (checkpointer), [#45](https://github.com/Finntegrate/tapio/issues/45) (partner reporting), and [#46](https://github.com/Finntegrate/tapio/issues/46) (partner dashboard) each assume an answer. Settled separately, they would settle it five different ways.

Three constraints from the PRD bound the answer.

- **No PII by default** (PRD §5). Many users are asylum seekers, undocumented, or fleeing abuse. For them a breach, a subpoena, or a compromised account can mean deportation or exposure to a persecutor. There is no minor-incident tier, so the safest record is the one that does not exist.
- **Access never requires proving identity or status** (PRD §7.6). Authentication exists to let someone come back to a conversation, not to establish who they are.
- **Partners see aggregate signals, not individuals** (PRD §7.7), and PRD §11 asks what "partner-affiliated" means before this is designed.

Operating budget also rules out a persistent managed database for now, so the design must work on embedded storage and move later without changing its shape.

## Decision

**Anonymous use is the default and is complete.** Everything a person needs to get a sourced answer works with no account. An anonymous conversation is held only for as long as it is useful and then expires.

**Accounts exist only to bring a conversation back.** An account is a random pseudonymous identifier plus the one thing needed to reach the person again: an email address, used for passwordless sign-in links. No name, no nationality, no phone number, no password, no third-party identity. Everything else in the system refers to the pseudonymous identifier, never to the email.

**No social login.** Signing in with a third-party identity provider hands that provider a record that this person uses an immigration assistant, and ties their Tapio account to an identity the person may be trying to keep separate. For this audience that is a disclosure, not a convenience. A signed link to an inbox the person already controls reveals less and is as low-friction.

**Three roles, one mechanism.** *Anonymous*, *registered*, and *partner administrator*. A partner administrator is a registered account that Finntegrate has granted administration of one organization; the role is granted by Finntegrate, never self-asserted, and carries no ability to read any user's conversation.

**A partner organization is a reporting and quota scope, not a data silo.** There is one shared corpus and one set of guides. A partner organization never owns, stores, or reads user data. It is a label that a person can opt into so that aggregate counts and usage budgets can be attributed to it.

**Partner affiliation is opt-in, revocable, and does not require an account.** A person arrives through a partner's referral and may be told so plainly; the attribution is theirs to keep or remove. Partners receive aggregates only, and an aggregate that could single out a person is withheld.

**Conversation ownership is enforced, not assumed.** A conversation is addressable only by an unguessable identifier, and every access checks that the caller owns it. A person can delete any conversation they own, and deleting removes it rather than hiding it.

**Conversation state lives in the LangGraph checkpointer, on embedded storage first.** Ownership and retention are kept beside the checkpoint rather than inside it, so the storage engine can change without touching the identity model.

**Retention is bounded by default.** Anonymous conversations expire quickly; registered conversations expire after a period of inactivity unless the person deletes them sooner.

## Consequences

### Positive

- The protective default holds for the people at greatest risk: someone who never creates an account leaves almost nothing behind.
- One identity model answers #31, #32, #35, #16, and #45 together, so they cannot disagree.
- Partners get the visibility the PRD promises without ever holding or being able to request individual records, which also means a partner cannot be compelled to produce them.
- Because partners are a scope rather than a tenant, there is no per-tenant data isolation to build, test, or get wrong.
- The identity model is independent of the storage engine, so the move off embedded storage is a migration, not a redesign.

### Negative

- An email address is still personal data, and holding it makes Tapio a controller of it with the obligations that follow (erasure, export, breach notification). The design minimizes this; it cannot remove it.
- Email delivery becomes a dependency of returning to a conversation, and a person who loses access to their inbox loses the conversation.
- Anonymous conversations are not recoverable after expiry, and a person who clears their browser state loses an in-progress anonymous conversation.
- Opt-in attribution undercounts. Partner figures describe people who chose to be counted, not everyone referred.
- Refusing social login removes the lowest-friction path for users who are comfortable with it.

### Risks

- Anonymous usage still has to be rate-limited, which tempts collecting a network identifier. A network address is personal data under GDPR, so whatever limits abuse must hold it briefly and not in a form that identifies a person.
- Small partners produce small aggregates. If the withholding rule is too lenient a partner can infer an individual; if too strict a small partner sees nothing useful. The threshold needs review against real pilot volumes.
- Free-text conversation content can contain anything a user volunteers. Minimizing account fields does not minimize what is typed into a conversation, so retention and deletion carry most of the protection.
- Controller status, lawful basis, and data-protection-officer questions are decided in [#40](https://github.com/Finntegrate/tapio/issues/40) and [#101](https://github.com/Finntegrate/tapio/issues/101). This ADR assumes those will not require collecting more than it proposes, and must be revisited if they do.

## Alternatives considered

### Require an account for everything

Rejected. It makes every user's first interaction a disclosure and turns a cold start into a barrier, for a population for whom that barrier is the reason not to use the service.

### Social login (Google, Apple, GitHub)

Rejected for the reasons above. It was named as preferred in the original issue on the grounds of low friction; the friction it removes is outweighed by the third-party linkage it creates.

### Passwords

Rejected. A password is a secret to store, breach, and reset, and the reset flow needs an email address anyway.

### Anonymous only, no accounts

Considered seriously, since it holds the least data. Rejected because returning to a multi-session permit process is a stated product need (PRD §7.6), and a device-bound anonymous conversation does not survive a lost phone or a change of device, which is common in this population.

### Partner organizations as full tenants

Rejected. Tenant-scoped data would imply partners hold and can read their users' records, contradicting PRD §7.7, and would add isolation machinery for a boundary that should not exist.

### Partner-issued accounts or membership lists

Rejected. A list of who a partner referred is exactly the identifiable record the privacy posture exists to avoid, and a partner holding one could be compelled to disclose it.

### Network-address-based identity for quotas

Rejected as a durable identifier. Retained only as a short-lived abuse signal under the constraint stated in Risks.

## References

- [Specification: authentication and tenancy](../specs/auth-and-tenancy.md) — the mechanism this decision commits to
- [PRD §5, §7.5–7.7, §11](../PRD.md)
- [#30: Design auth and tenancy model](https://github.com/Finntegrate/tapio/issues/30)
- [#16](https://github.com/Finntegrate/tapio/issues/16), [#31](https://github.com/Finntegrate/tapio/issues/31), [#32](https://github.com/Finntegrate/tapio/issues/32), [#35](https://github.com/Finntegrate/tapio/issues/35), [#40](https://github.com/Finntegrate/tapio/issues/40), [#45](https://github.com/Finntegrate/tapio/issues/45), [#46](https://github.com/Finntegrate/tapio/issues/46), [#101](https://github.com/Finntegrate/tapio/issues/101)
- [ADR 0005: Shared, guide-led conversation](0005-multi-agent-chat-experience.md)
