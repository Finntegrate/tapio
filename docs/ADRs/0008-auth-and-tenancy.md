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

The threat model is not only an outside attacker. A controlling partner or family member may share the person's device, read their inbox, or try to steer them into using an account the abuser controls. Shared computers in libraries and reception centres are ordinary for this population.

Operating budget also rules out a persistent managed database for now, so the design must work on embedded storage and move later without changing its shape.

## Decision

**Anonymous use is the default and is complete.** Everything a person needs to get a sourced answer works with no account. An anonymous session lasts no longer than the browser session, and its conversations expire soon after. During the beta, admission requires an access code distributed through partners ([ADR 0009](0009-abuse-and-cost-controls.md)); the code admits a person without identifying them, and needing one does not change what anonymous use can do once admitted.

**Accounts exist only to bring a conversation back, and hold no readable contact details.** An account is a random pseudonymous identifier and a keyed hash of an email address. A person signs in by typing their address and then a one-time code sent to it, in the same browser. The service uses the typed address to send that one message and keeps only the hash, so it can recognize the address when it is typed again but cannot read it, contact the person, or hand it over. No name, nationality, phone number, password, or third-party identity is collected.

**No social login.** Signing in with a third-party identity provider hands that provider a record that this person uses an immigration assistant, and ties their Tapio account to an identity the person may be trying to keep separate. For this audience that is a disclosure, not a convenience.

**Sign-in completes only in the browser that asked for it.** A code is entered, not a link followed, so it cannot be completed on another device, consumed by a mail scanner, or used to sign a victim's browser into someone else's account.

**Three roles, one mechanism.** *Anonymous*, *registered*, and *partner administrator*. A partner administrator is a registered account that Finntegrate has granted administration of one organization; the role is granted by Finntegrate, never self-asserted, and carries no ability to read any user's conversation.

**A partner organization is a reporting and quota scope, not a data silo.** There is one shared corpus and one set of guides. A partner organization never owns, stores, or reads user data. It is a label that a person can choose to be counted under, so that aggregate figures and usage budgets can be attributed to it.

**Partner affiliation is opt-in, revocable, and does not require an account.** A person who arrives through a partner is told so plainly and is counted for that partner only if they choose to be. The choice is off until they make it, and they can undo it. Partners receive a fixed set of organization-level aggregate reports, and a figure that could single out a person is withheld.

**Conversation ownership is enforced, not assumed.** A conversation is addressable only by an unguessable identifier, and every access checks that the caller owns it. A person can delete any conversation they own, and deletion makes it unreadable. Where history lives and how it is protected at rest is decided in [ADR 0010](0010-server-held-conversation-history.md).

**Identity and ownership are kept apart from conversation storage.** Accounts, sessions, ownership, and retention live beside the conversation store rather than inside it, so either can change engine without touching the identity model.

**Retention is bounded by default.** Every conversation expires automatically after a short default period ([ADR 0010](0010-server-held-conversation-history.md)), and an account no one signs in to expires too.

## Consequences

### Positive

- The protective default holds for the people at greatest risk: someone who never creates an account leaves nothing that outlives a short expiry and nothing readable at rest.
- An account breach, disk image, or legal demand yields no email addresses, only hashes that can confirm an address someone already knows, and only with the service's key.
- Sign-in cannot be completed from a link someone else forwarded, so an abuser cannot quietly sign a victim's browser into the abuser's account and read what the victim types next.
- One identity model answers #31, #32, #35, #16, and #45 together, so they cannot disagree.
- Partners get the visibility the PRD promises without ever holding or being able to request individual records, which also means a partner cannot be compelled to produce them.
- Because partners are a scope rather than a tenant, there is no per-tenant data isolation to build, test, or get wrong.

### Negative

- An email hash is still personal data, and holding it makes Tapio a controller of it, with the obligations that follow. The design minimizes this; it cannot remove it. The PRD's no-contact-details rule is amended to allow exactly this.
- The service cannot email a person, so there are no expiry warnings, no sign-in alerts, and no recovery path other than signing in again. Expiry dates are shown in the interface instead.
- Whoever controls a person's inbox can sign in as them. The interface advises using an address no one else reads, and offers signing out everywhere.
- Typing a code is slightly more effort than following a link.
- Anonymous conversations are not recoverable after the browser closes or the session expires.
- Opt-in attribution undercounts. Partner figures describe people who chose to be counted, not everyone referred.
- Refusing social login removes the lowest-friction path for users who are comfortable with it.

### Risks

- Anonymous usage still has to be bounded against abuse, which tempts collecting a network identifier. [ADR 0009](0009-abuse-and-cost-controls.md) decides how; whatever it does must hold a network address briefly and not in a form that identifies a person, since it is personal data under GDPR.
- Small partners produce small aggregates. If the withholding rule is too lenient a partner can infer an individual; if too strict a small partner sees nothing useful. Employer partners carry a particular risk, since they hold power over the people they refer.
- Free-text conversation content can contain anything a user volunteers. Minimizing account fields does not minimize what is typed into a conversation; [ADR 0010](0010-server-held-conversation-history.md) carries most of that protection.
- Controller status, lawful basis, and data-protection-officer questions are decided in [#40](https://github.com/Finntegrate/tapio/issues/40) and [#101](https://github.com/Finntegrate/tapio/issues/101). This ADR assumes those will not require collecting more than it proposes, and must be revisited if they do.
- The access-code gate suspends "anonymous use is complete" for the duration of the beta. [ADR 0009](0009-abuse-and-cost-controls.md) states when the gate is reviewed.

## Alternatives considered

### Require an account for everything

Rejected. It makes every user's first interaction a disclosure and turns a cold start into a barrier, for a population for whom that barrier is the reason not to use the service.

### Social login (Google, Apple, GitHub)

Rejected for the reasons above. It was named as preferred in the original issue on the grounds of low friction; the friction it removes is outweighed by the third-party linkage it creates.

### Passwords

Rejected. A password is a secret to store, breach, and reset, and the reset flow needs an email address anyway.

### Sign-in links

Rejected. A link can be completed in any browser that opens it, which lets an abuser sign a victim's browser into the abuser's own account by sending them the link. Corporate and NGO mail scanners open links before people do, consuming single-use tokens. Binding a link to the requesting browser needs a fallback code anyway, so the code alone is simpler.

### Keep the email address in readable form

Rejected. Its only uses would be sending sign-in codes, which the person's own typing already covers, and sending warnings, which would themselves disclose Tapio use to whoever reads the inbox. A readable address is what a breach or a demand would be after.

### Anonymous only, no accounts

Considered seriously, since it holds the least data. Rejected because returning to a multi-session permit process is a stated product need (PRD §7.6), and a device-bound anonymous conversation does not survive a lost phone or a change of device, which is common in this population.

### Partner organizations as full tenants

Rejected. Tenant-scoped data would imply partners hold and can read their users' records, contradicting PRD §7.7, and would add isolation machinery for a boundary that should not exist.

### Partner-issued accounts or membership lists

Rejected. A list of who a partner referred is exactly the identifiable record the privacy posture exists to avoid, and a partner holding one could be compelled to disclose it.

### Network-address-based identity for quotas

Rejected as a durable identifier. Retained only as a short-lived abuse signal, as [ADR 0009](0009-abuse-and-cost-controls.md) specifies.

## References

- [Specification: authentication and tenancy](../specs/auth-and-tenancy.md) — the mechanism this decision commits to
- [ADR 0009: Abuse and cost controls](0009-abuse-and-cost-controls.md)
- [ADR 0010: Server-held conversation history](0010-server-held-conversation-history.md)
- [PRD §5, §7.5–7.7, §10, §11](../PRD.md)
- [#30: Design auth and tenancy model](https://github.com/Finntegrate/tapio/issues/30)
- [#16](https://github.com/Finntegrate/tapio/issues/16), [#31](https://github.com/Finntegrate/tapio/issues/31), [#32](https://github.com/Finntegrate/tapio/issues/32), [#35](https://github.com/Finntegrate/tapio/issues/35), [#40](https://github.com/Finntegrate/tapio/issues/40), [#45](https://github.com/Finntegrate/tapio/issues/45), [#46](https://github.com/Finntegrate/tapio/issues/46), [#101](https://github.com/Finntegrate/tapio/issues/101)
- [ADR 0005: Shared, guide-led conversation](0005-multi-agent-chat-experience.md)
