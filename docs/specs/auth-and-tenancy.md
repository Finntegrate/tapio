# Authentication and tenancy — specification

**Status:** Proposed

**Owner:** Finntegrate

**Related architecture:** [ADR 0008](../ADRs/0008-auth-and-tenancy.md), [ADR 0010](../ADRs/0010-server-held-conversation-history.md)

## Problem statement

Saved conversations, usage quotas, and partner reporting all depend on knowing who a request is from and what may be remembered about them. Tapio's users include people for whom an identity record is a hazard (PRD §5), and people whose device or inbox may be shared with someone they fear, so the design has to give them the useful parts of an account without the record. This specification defines the identity model, sign-in, sessions, partner affiliation, and conversation ownership. How conversations themselves are stored, encrypted, deleted, and expired is in [conversation history](conversation-history.md). Which of these is a decision and why is in [ADR 0008](../ADRs/0008-auth-and-tenancy.md); this document is the mechanism and is revised as implementation proceeds.

## Goals

1. Everything needed to get a sourced answer works with no account.
2. An account holds the least data that lets a person return to a conversation, and nothing readable that could contact them.
3. Partners can be counted and budgeted without holding or requesting any individual record.
4. Conversation access is checked on every request, not implied by knowing an identifier.
5. Sign-in cannot be completed in a browser other than the one that started it.

## Non-goals

- **Identity verification.** Nothing in Tapio proves who someone is or what status they hold (PRD §7.6).
- **Case data.** Tapio does not hold case numbers, application status, or family details (PRD §5, §7.5).
- **Billing or paid tiers.** Quota tiers exist for cost control, not monetization.
- **A partner-facing user directory.** Partners never receive a list of people.

## Principals

| Principal | How established | Can do | Holds |
| --- | --- | --- | --- |
| **Anonymous** | A random session secret issued on admission and kept by the browser for the browser session | Chat; keep a conversation until it expires | Session id; its conversations |
| **Registered** | A one-time code emailed to an address and entered in the same browser | Everything anonymous can; resume conversations across devices; name and delete conversations | Account id; email hash; its conversations |
| **Partner administrator** | A registered account granted administration of one organization by a Finntegrate operator | Everything registered can; read that organization's reports and quota usage | A role grant on one organization |

A partner administrator has no read access to any user's conversation, whether or not that user is affiliated with the administrator's organization. The role is granted and revoked only by a Finntegrate operator through an operator tool, never through the public API. The role rests on control of an inbox, which is adequate for reading aggregates; passkeys are the upgrade path if the role ever carries more.

Roles are checked server-side from the authenticated principal. A client-supplied role, organization, or account id is never trusted.

## Account data

An account record contains exactly:

| Field | Purpose |
| --- | --- |
| `account_id` | Random, non-derivable identifier; the only key other tables use |
| `email_hash` | HMAC-SHA-256 of the normalized address, with the [key](#keys) version it was made with; used only to find the account when the address is typed again |
| `created_at`, `last_sign_in_at` | Account expiry |
| `partner_affiliation` | Optional; see [Partner affiliation](#partner-affiliation) |

The service does not store the email address. It holds the typed address in memory only for as long as it takes to hand one message to the mail processor. No name, nationality, phone number, password, or third-party identity is collected. Neither the address nor its hash is ever written to a log, an analytics event, a checkpoint, or a partner report.

An account with no sign-in for 180 days is deleted, with any conversations it still owns. The interface states this rule, since the service has no way to warn the person.

A signed-in person can delete their account at any time. Deletion removes the account record, its sessions, every conversation it owns ([conversation history](conversation-history.md#deletion)), and its affiliation, and is not recoverable.

## Sign-in

1. The person types an email address. The server sets a random sign-in cookie on that browser and creates a pending sign-in holding a hash of that cookie, the email hash, a hash of a fresh 6-digit code, an expiry of 10 minutes, and an attempt count. The cookie is named with the `__Host-` prefix, is `HttpOnly`, `Secure`, `SameSite=Strict`, and `Path=/`, and expires after 10 minutes.
2. The server sends the code to the typed address and discards the address.
3. The person types the code into the same browser. The server accepts it only if the request carries the sign-in cookie of that pending sign-in, the code matches, the sign-in has not expired, and fewer than 5 attempts have been made. The fifth wrong code discards the pending sign-in.
4. On success the server finds or creates the account and issues a registered session, as one write transaction: it looks the address up under every active key version, creates an account only if none matches, and relies on a uniqueness constraint on the email hash so that two concurrent sign-ins for one address cannot create two accounts. The pending sign-in is deleted.

Whenever a pending sign-in ends — success, expiry, or the fifth wrong code — the server deletes it and clears the sign-in cookie.

The response to step 1 is the same whether or not the address has an account. Requests are rate limited per email hash (5 per hour) and per network bucket ([abuse and cost controls](abuse-and-cost-controls.md#rate-limits)).

A code cannot be completed in a browser that did not request it, so a forwarded code or a mail scanner cannot complete sign-in, and nothing in the mail is a link to follow. The mail contains the code and a plain-language line saying someone asked to sign in. It names the product only as much as is needed for the recipient to recognize it, because a shared inbox may be read by someone the person fears. Email is sent through a processor operating in the EU under a data-processing agreement.

There is no social login and no password.

## Sessions

Every session is an opaque random secret in a cookie. The server stores only a value derived from it.

| Session | Cookie lifetime | Server-side lifetime |
| --- | --- | --- |
| Anonymous | Browser session; no stored expiry | Conversations and session deleted after 24 hours idle or 7 days, per [retention](conversation-history.md#retention) |
| Registered | 7 days idle, 30 days absolute | The same, revoked on sign-out |

Session cookies use the `__Host-` prefix and are `HttpOnly`, `Secure`, and `SameSite=Lax`.

A registered person can see their active sessions, each by when it signed in and was last used, and can sign out of any of them or all of them at once.

### Anonymous sessions

Admission issues a random session secret. From it the server derives the session id it stores and the key that encrypts the session's conversations ([conversation history](conversation-history.md#anonymous-conversations)).

During the beta, admission requires redeeming an access code distributed by a partner organization. The code admits; it does not identify. Codes are shared by many people, and how they are generated, stored, redeemed, and protected against guessing is specified in [abuse and cost controls](abuse-and-cost-controls.md#access-codes). Once the beta gate is lifted, admission happens on first use.

The interface always shows a control to end the session. Ending it deletes the session's conversations and clears the browser's state ([conversation history](conversation-history.md#deletion)).

### Claiming conversations on sign-in

When an anonymous person signs in, the interface offers to move their current anonymous conversations into the account, showing the address they have just typed so they can see whose account it is. The address is shown from what the browser already has; the server cannot show it later. This is an explicit action. Nothing is migrated silently, and declining leaves the conversations to expire.

### Shared devices and inboxes

- The interface tells people on a shared computer to end the session when they leave, and the end-session control is always visible.
- Whoever can read a person's inbox can sign in as them. The sign-in screen advises using an address no one else reads. There is no sign-in alert by email, both because the service keeps no address and because the alert would itself disclose Tapio use to whoever reads the inbox.

## Web security

- The web app and the API are served from one origin through the hosting edge, so session cookies are first-party and the API needs no cross-origin credentials.
- State-changing requests must carry an `Origin` header matching the service's origin and a JSON body.
- Pages are served with a Content Security Policy that allows scripts only from the service's own origin, and with `Referrer-Policy: no-referrer`. No third-party script runs on any page, since a script on the page can read an access code from the URL fragment and the conversation from the document.

## Partner affiliation

A partner organization is a record with an id, a display name, a type (for example NGO, municipality, or employer), and one or more codes. It is not a container for users.

During the beta, a partner's access code is also its referral code. Redeeming it does not create an affiliation. The session records which code admitted it only so that the code can be revoked and its usage limited ([abuse and cost controls](abuse-and-cost-controls.md#redemption)). Per-code figures are operator-only and are never shared with a partner, including informally.

### How affiliation is established

On arrival through a partner's code, the interface states, in plain language, which organization referred the visit, and asks whether the person wants to be counted in that organization's aggregate figures. The choice is off until the person turns it on. Affiliation is stored only when they do.

- An anonymous principal's affiliation is held on the session and expires with it.
- A registered principal's affiliation is held on the account.
- A principal has at most one affiliation. A newer referral replaces an older one only with the person's confirmation.
- A person can remove their affiliation at any time from the same place they can delete conversations. Removal takes effect for all future reporting.
- Affiliation grants the partner nothing beyond inclusion in counts. It carries no access to the person or their conversations.

### What a partner can see

A partner administrator sees a fixed set of reports for their organization, computed per calendar month at organization level, never per code:

- affiliated sessions and returning sessions,
- sessions by guide and by topic category,
- quota consumption.

There are no ad-hoc filters, custom date ranges, or per-code breakdowns, so no two reports can be subtracted to isolate a person. Any figure below a minimum cell size (initially 10) is withheld and reported as "fewer than 10". Guardrail categories (`crisis`, `legal_sensitive`) are never reported to partners. For employer partners, topic breakdowns are withheld entirely, since an employer holds power over the people it refers. Reports are built from aggregate counts, never from rows keyed to a person or conversation, and contain no message content.

Which events feed these counts, and the consent that covers collecting them, is decided in [#101](https://github.com/Finntegrate/tapio/issues/101) and [#45](https://github.com/Finntegrate/tapio/issues/45); this specification only fixes the boundary that they must produce these aggregates and nothing finer. The list above is the whole report set. Outcome signals, which PRD §7.7 anticipates, join it only when those issues define each signal, its source event, and its consent, and every signal added is subject to the same monthly organization-level aggregation, minimum cell size, and exclusions.

## Conversation ownership

A conversation is identified by a `thread_id` that is a random 128-bit value. It is a handle, not a credential.

An ownership record, kept beside the checkpointer and not inside it, binds each `thread_id` to exactly one principal. Every endpoint that reads, extends, lists, renames, or deletes a conversation resolves the caller to a principal and requires that the principal owns the `thread_id`. A request naming a `thread_id` the caller does not own receives the same response as one naming a nonexistent `thread_id`.

A new conversation is created by the server, which mints the `thread_id`; the client never chooses one.

Conversations are listed only for the calling principal. An anonymous principal lists the conversations of its own session.

History, turns, encryption, deletion, and retention are specified in [conversation history](conversation-history.md).

## Keys

Every server-held key — the email-hash key, the access-code hash key, and the key-encryption key for registered conversations — lives in the deployment's secret store, never in the repository or the database. Every hash or wrapped key records the version of the key that made it.

Rotation adds a new version. Lookups try every active version; an email hash is rewritten with the newest version when the person next signs in, and an access code hashed with an old version stays valid until the code expires or is reissued. A version is retired once nothing references it. The network-bucket key is not stored at all; see [abuse and cost controls](abuse-and-cost-controls.md#rate-limits).

## Quotas and abuse controls

Budgets, admission, rate limits, the spend ceiling, and the controls that keep an anonymous endpoint from being used to spend the project's money are specified in [abuse and cost controls](abuse-and-cost-controls.md), under [ADR 0009](../ADRs/0009-abuse-and-cost-controls.md). This specification fixes only what they must not do: any network-derived value is an abuse signal held briefly and never joined to an account, a conversation, or a partner report.

## Storage

Accounts, sessions, pending sign-ins, ownership, affiliation, access codes, and conversation data keys are held in one embedded SQLite store, separate from the checkpoint store, behind an interface that does not expose the engine. Moving it off embedded storage changes the implementation behind that interface and no identifiers, ownership rules, or retention behaviour.

Embedded storage is single-writer. The deployment runs as one process until a move is warranted.

## Operator tooling

Finntegrate operators, not the public API, can create and retire partner organizations, issue and revoke access codes, and grant and revoke partner administration. Operator actions are logged with the operator and action, never with conversation content or an email address.

There is no operator tool to read a conversation. Anonymous conversations are unreadable at rest without the person's browser. Registered conversations are encrypted with keys the service holds, so someone with access to both the host and its secrets could read them; the privacy notice says exactly that rather than claiming otherwise.

Account deletion is self-service after sign-in, which is the proof that the account is the requester's. Operators do not delete an account on an unverified request, since doing so would let anyone erase someone else's history; an account no one can sign in to expires on its own.

## Failure modes

| Case | Behaviour |
| --- | --- |
| Sign-in code wrong, expired, or entered in another browser | Generic message offering a new code; the fifth wrong code ends that sign-in |
| `thread_id` not owned by caller | Same response as a nonexistent conversation |
| Anonymous session cookie lost | The conversation cannot be read again; the interface says so up front |
| Email unreachable | No recovery path; there is nothing to reset |
| Partner figure below threshold | Withheld, reported as below the minimum |
| Partner administration revoked | Takes effect on the next request |

## Testing

- Ownership: a principal cannot read, extend, list, rename, or delete another principal's conversation, and the response is indistinguishable from "not found".
- Roles: a partner administrator cannot read any conversation, including those of affiliated users.
- Account data: no stored row, log line, analytics event, checkpoint, or report contains an email address; a test asserts this against the stores and captured output of a full sign-in and chat flow.
- Sign-in binding: a correct code submitted from a browser without the pending sign-in's cookie does not sign in and does not claim conversations.
- Sign-in: codes are single-use, expire, and stop working after five wrong attempts; the response to a request does not reveal whether an address is registered; the sign-in cookie is cleared when its pending sign-in ends.
- Accounts: two concurrent successful sign-ins for one new address produce one account.
- Affiliation: arriving with a partner code and taking no action stores no affiliation.
- Reports: no report has a figure below the threshold, a per-code breakdown, a guardrail category, or, for an employer, a topic breakdown.
- Sessions: signing out everywhere ends every session of the account on its next request.
- Web security: a state-changing request with a foreign or missing `Origin` is refused.
- Abuse signals: a network-derived value is never persisted past its time-to-live and never appears in an account or partner record.

## Delivery

This design unblocks, and constrains, the implementation issues that follow: [#31](https://github.com/Finntegrate/tapio/issues/31) for sign-in and ownership, [#16](https://github.com/Finntegrate/tapio/issues/16) for the checkpointer, [#35](https://github.com/Finntegrate/tapio/issues/35) for saved conversations, [#32](https://github.com/Finntegrate/tapio/issues/32) for quotas, and [#45](https://github.com/Finntegrate/tapio/issues/45) and [#46](https://github.com/Finntegrate/tapio/issues/46) for partner reporting.

The beta needs anonymous sessions, access codes, ownership, the web security above, and [server-held history](conversation-history.md#delivery). Accounts and partner reports come after it.

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Lawful basis and controller obligations for holding an email hash, and whether a Data Protection Officer or notification is required | Privacy and data ([#40](https://github.com/Finntegrate/tapio/issues/40)) | Yes, before accounts ship |
| Which usage events feed partner reports, and what consent covers collecting them | Privacy and data ([#101](https://github.com/Finntegrate/tapio/issues/101)) | Yes, before partner reporting |
| Is a minimum cell size of 10 right for pilot volumes, and should employers have a higher one | Product and partnerships | No; configuration |
| Should passkeys be offered as a second sign-in method | Product and engineering | No |
| Which EU email processor, and does its retention of delivery logs fit the retention policy | Engineering, privacy | Yes, before accounts ship |
