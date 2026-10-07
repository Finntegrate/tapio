# Authentication and tenancy — specification

**Status:** Proposed

**Owner:** Finntegrate

**Related architecture:** [ADR 0008](../ADRs/0008-auth-and-tenancy.md)

## Problem statement

Saved conversations, usage quotas, and partner reporting all depend on knowing who a request is from and what may be remembered about them. Tapio's users include people for whom an identity record is a hazard (PRD §5), so the design has to give them the useful parts of an account without the record. This specification defines the identity model, sign-in, partner affiliation, conversation ownership, quota scoping, and retention. Which of these is a decision and why is in [ADR 0008](../ADRs/0008-auth-and-tenancy.md); this document is the mechanism and is revised as implementation proceeds.

## Goals

1. Everything needed to get a sourced answer works with no account.
2. An account holds the least data that lets a person return to a conversation.
3. Partners can be counted and budgeted without holding or requesting any individual record.
4. Conversation access is checked on every request, not implied by knowing an identifier.
5. The identity model survives a change of storage engine.

## Non-goals

- **Identity verification.** Nothing in Tapio proves who someone is or what status they hold (PRD §7.6).
- **Case data.** Tapio does not hold case numbers, application status, or family details (PRD §5, §7.5).
- **Billing or paid tiers.** Quota tiers exist for cost control, not monetization.
- **A partner-facing user directory.** Partners never receive a list of people.
- **Choosing the production database.** Storage is embedded first; see [Storage](#storage).

## Principals

| Principal | How established | Can do | Holds |
| --- | --- | --- | --- |
| **Anonymous** | A random session secret issued on admission and kept by the browser | Chat; keep a conversation until it expires | Session secret hash; its conversations |
| **Registered** | Passwordless sign-in link to an email address | Everything anonymous can; resume conversations across devices; name and delete conversations | Account id; email; its conversations |
| **Partner administrator** | A registered account granted administration of one organization by a Finntegrate operator | Everything registered can; read that organization's aggregate report and quota usage | A role grant on one organization |

A partner administrator has no read access to any user's conversation, whether or not that user is affiliated with the administrator's organization. The role is granted and revoked only by a Finntegrate operator through an operator tool, never through the public API.

Roles are checked server-side from the authenticated principal. A client-supplied role, organization, or account id is never trusted.

## Account data

An account record contains exactly:

| Field | Purpose |
| --- | --- |
| `account_id` | Random, non-derivable identifier; the only key other tables use |
| `email` | Sending sign-in links; nothing else |
| `created_at`, `last_seen_at` | Retention |
| `partner_affiliation` | Optional; see [Partner affiliation](#partner-affiliation) |

No name, nationality, phone number, password, or third-party identity is collected. The email address is never written to a log, an analytics event, a checkpoint, or a partner report. Looking up an account by email uses a keyed hash of the address; the plain address is retained only to send mail and is deleted with the account.

An account is deleted on request. Deletion removes the account record, every conversation it owns, and its affiliation, and is not recoverable.

## Sign-in

Sign-in is a single-use link sent to the address the person gives.

- The link carries a random token. Only a hash of the token is stored.
- Tokens are single-use and expire after 15 minutes.
- Requesting a link for an address that has no account creates one on use of the link, so the response to a request never reveals whether an address is registered.
- Link requests are rate limited per address and per network bucket.
- A successful sign-in issues an opaque session cookie, `HttpOnly`, `Secure`, `SameSite=Lax`, with a sliding idle expiry and a fixed absolute expiry. Signing out revokes the session server-side.
- Sign-in mail contains only the link and a plain-language line saying someone requested it. It names the product only as much as is needed for the recipient to recognize it, because a shared inbox may be read by someone the person fears.
- Email is sent through a processor operating in the EU under a data-processing agreement.

There is no social login and no password. Passkeys are a candidate later addition that would add a sign-in method without adding a stored identity attribute.

## Anonymous sessions

Admission issues a random session secret, stored as a cookie. The server keeps only its hash. An anonymous principal's id is derived from that hash and is not stable across devices.

During the beta, admission requires redeeming an access code distributed by a partner organization. The code admits; it does not identify. Codes are shared by many people, and how they are generated, stored, redeemed, and protected against guessing is specified in [abuse and cost controls](abuse-and-cost-controls.md#access-codes). Once the beta gate is lifted, admission happens on first use.

An anonymous conversation expires after a short idle period and a fixed maximum age, whichever comes first. The interface says so before the person invests in a long conversation.

### Claiming conversations on sign-in

When an anonymous person signs in, the interface offers to move their current anonymous conversations into the account. This is an explicit action. Nothing is migrated silently, and declining leaves them to expire.

## Partner affiliation

A partner organization is a record with an id, a display name, and one or more codes. It is not a container for users.

During the beta, a partner's access code is also its referral code: the code that admits a person is what lets the interface offer affiliation. Redeeming it does not create an affiliation. The session holds which code admitted it only so that the code can be revoked and its usage limited; that is not reported to the partner unless the person accepts affiliation.

### How affiliation is established

A partner distributes its code, or a link carrying it. On arrival the interface states, in plain language, that the visit was referred by that organization and that Tapio will count it in the organization's aggregate figures, and offers to turn that off. Affiliation is stored only if the person does not decline.

- An anonymous principal's affiliation is held on the session and expires with it.
- A registered principal's affiliation is held on the account.
- A principal has at most one affiliation. A newer referral replaces an older one only with the person's confirmation.
- A person can remove their affiliation at any time from the same place they can delete conversations. Removal takes effect for all future reporting.
- Affiliation grants the partner nothing beyond inclusion in counts. It carries no access to the person or their conversations.

### What a partner can see

A partner administrator sees, for their organization only:

- counts of affiliated sessions and returning sessions over time,
- counts by guide and by topic category,
- quota consumption for the organization.

The report is built from aggregate counts, never from rows keyed to a person or conversation, and contains no message content.

A count below a minimum cell size (initially 10) is withheld and reported as "fewer than 10". The threshold applies to every breakdown and to the difference between any two cuts a partner can request, so that two permitted reports cannot be subtracted to isolate a person. The threshold is configuration, reviewed against real pilot volumes.

Which events feed these counts, and the consent that covers collecting them, is decided in [#101](https://github.com/Finntegrate/tapio/issues/101) and [#45](https://github.com/Finntegrate/tapio/issues/45); this specification only fixes the boundary that they must produce aggregates and nothing finer.

## Conversation ownership

A conversation is identified by a `thread_id` that is a random 128-bit value. It is a handle, not a credential.

An ownership record, kept beside the checkpointer and not inside it, binds each `thread_id` to exactly one principal. Every endpoint that reads, extends, lists, renames, or deletes a conversation resolves the caller to a principal and requires that the principal owns the `thread_id`. A request naming a `thread_id` the caller does not own receives the same response as one naming a nonexistent `thread_id`.

A new conversation is created by the server, which mints the `thread_id`; the client never chooses one.

Conversations are listed only for the calling principal. An anonymous principal lists the conversations of its own session.

### The server holds the history

The server is the only source of a conversation's history, for every principal, anonymous included. A turn request carries the `thread_id` and the new message, nothing else from the conversation. The server loads prior turns from the checkpointer, decides how much of them to send to the model, runs the turn, and persists both the person's message and the guide's answer before acknowledging it.

The API accepts no client-supplied history. A request that carries one is rejected, not silently ignored, so a client bug is visible rather than masked. This removes two attacks at once: fabricated earlier turns, including forged guide answers written to steer the model, and inflated input that the project pays for on every request.

The client hydrates from the server and renders optimistically:

- On opening a conversation, the client fetches its turns from the server and renders them.
- On sending, the client shows the person's message immediately as pending. The server's first stream event acknowledges it with a server-assigned message id, and the client marks it sent.
- Streamed answer text is rendered as it arrives and replaced by the persisted answer when the turn completes.
- If the turn fails or is refused, the pending message is marked as not sent and its text stays in the input for retry; nothing is persisted for a turn the server did not accept.
- After a reconnect, or when a stream ends without a completion event, the client refetches the conversation rather than trusting what it rendered.

The client's copy is a cache. Where it and the server disagree, the server wins.

### Deletion

Deleting a conversation removes its checkpoints and its ownership record. There is no soft delete and no archive. Deletion is idempotent.

### Retention

| Principal | Default retention |
| --- | --- |
| Anonymous | Expires after 24 hours idle, 7 days absolute |
| Registered | Expires after 90 days idle unless deleted sooner |

A scheduled job deletes expired conversations and expired anonymous sessions. Retention values are configuration. Registered users are warned by email before expiry only if they opted in; the default is to expire without notice, because mail about an immigration assistant can itself expose someone.

Free-text content in a conversation can include anything the person typed. Account minimization does not reduce that, so the guidance to avoid sharing identifying details (PRD §7.5) and the retention bound are the controls that apply to it.

## Quotas and abuse controls

Budgets, edge limits, the global spend ceiling, and the controls that keep an anonymous endpoint from being used to spend the project's money are specified in [abuse and cost controls](abuse-and-cost-controls.md), under [ADR 0009](../ADRs/0009-abuse-and-cost-controls.md). This specification fixes only what they must not do: any network-derived value is an abuse signal held briefly and never joined to an account, a conversation, or a partner report.

## Storage

Every conversation, including an anonymous one for its short lifetime, is held in a LangGraph checkpointer ([#16](https://github.com/Finntegrate/tapio/issues/16)). The first implementation uses an embedded SQLite-backed checkpointer, consistent with the project having no operating budget for a persistent managed database. In-memory storage is used for local development and tests only.

Account, session, ownership, affiliation, and quota records are stored in a separate store from the checkpoints, behind an interface that does not expose the engine. Moving either store off embedded storage changes the implementation behind that interface and no identifiers, ownership rules, or retention behaviour.

Embedded storage is single-writer. The deployment runs as one process until a move is warranted; running more than one worker against the same embedded store is not supported.

Both stores are encrypted at rest. Backups follow the same retention as live data, so a deleted conversation does not survive in a backup past the backup window, which is stated in the privacy notice.

## Operator tooling

Finntegrate operators, not the public API, can create and retire partner organizations, issue and revoke access codes, grant and revoke partner administration, and delete an account on a person's request. Operator actions are logged with the operator and action but never the content of any conversation. There is no operator capability to read a user's conversation.

## Failure modes

| Case | Behaviour |
| --- | --- |
| Sign-in link expired or reused | Generic message offering a new link |
| `thread_id` not owned by caller | Same response as a nonexistent conversation |
| Anonymous session cookie lost | The conversation is not recoverable; the interface says so up front |
| Email unreachable | No recovery path beyond a new link; there is nothing to reset |
| Partner aggregate below threshold | Withheld, reported as below the minimum |
| Partner administration revoked | Takes effect on the next request |

## Testing

- Ownership: a principal cannot read, extend, list, rename, or delete another principal's conversation, and the response is indistinguishable from "not found".
- Roles: a partner administrator cannot read any conversation, including those of affiliated users.
- Account data: no log line, analytics event, checkpoint, or report contains an email address; a test asserts this against captured output of a full sign-in and chat flow.
- Sign-in: tokens are single-use, expire, and the response does not reveal whether an address is registered.
- History: a turn request carrying client-supplied history is rejected; the model receives only server-held turns; a refused or failed turn persists nothing.
- Deletion: after deleting a conversation or account, no checkpoint or ownership row remains.
- Retention: the expiry job removes conversations past their bound and leaves those inside it.
- Aggregates: any breakdown, and any pair of breakdowns whose difference could isolate fewer than the minimum, is withheld.
- Abuse signals: a network-derived value is never persisted past its time-to-live and never appears in an account or partner record.

## Delivery

This design unblocks, and constrains, the implementation issues that follow: [#31](https://github.com/Finntegrate/tapio/issues/31) for sign-in and ownership, [#16](https://github.com/Finntegrate/tapio/issues/16) for the checkpointer, [#35](https://github.com/Finntegrate/tapio/issues/35) for saved conversations, [#32](https://github.com/Finntegrate/tapio/issues/32) for quotas, and [#45](https://github.com/Finntegrate/tapio/issues/45) and [#46](https://github.com/Finntegrate/tapio/issues/46) for partner reporting. Moving history to the server is a prerequisite for opening the beta, because the current API accepts client-supplied history of any length. Server-held conversations ship with the retention and deletion defined here, as the [multi-agent chat specification](multi-agent-chat.md) requires; registered accounts that keep conversations for longer also wait on the lawful-basis decision in [#40](https://github.com/Finntegrate/tapio/issues/40).

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Lawful basis and controller obligations for holding an email address, and whether a Data Protection Officer or notification is required | Privacy and data ([#40](https://github.com/Finntegrate/tapio/issues/40)) | Yes, before accounts ship |
| Which usage events feed partner aggregates, and what consent covers collecting them | Privacy and data ([#101](https://github.com/Finntegrate/tapio/issues/101)) | Yes, before partner reporting |
| Is a minimum cell size of 10 right for pilot volumes | Product and partnerships | No; configuration |
| Should passkeys be offered as a second sign-in method | Product and engineering | No |
| Which EU email processor, and does its retention of delivery logs fit the retention policy | Engineering, privacy | Yes, before accounts ship |
