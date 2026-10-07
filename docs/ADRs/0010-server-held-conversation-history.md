# ADR 0010: The server holds conversation history, encrypted and kept only briefly

## Status

Proposed

## Date

2026-10-07

## Context

The current chat API accepts a conversation's earlier turns from the client on every request, of any length. That has two consequences. A client can forge earlier turns, including answers a guide never gave, to steer the next answer. And a client can inflate the input the project pays for on every call. Both are cheap to exploit against a public endpoint ([ADR 0009](0009-abuse-and-cost-controls.md)).

Moving history to the server closes both, but it reverses a privacy property. Client-held history means an anonymous conversation is stored nowhere Tapio controls. Server-held history means every conversation, anonymous ones included, exists on Tapio's disk for its lifetime. The PRD's principle is that the safest record is the one that does not exist (PRD §5). Conversations from this population routinely contain special-category data under GDPR Art. 9: health, religion, political opinion, sexual orientation, the grounds people seek asylum on. A record of them can be breached, imaged, or demanded.

So the question is not only where history lives but what a copy of the server's disk, a backup, or a legal demand can yield.

Two further facts bear on it.

- **Deleting a row is not deleting the data.** An embedded database leaves deleted content in free pages and its write-ahead log, and a checkpointer keeps every intermediate step of a conversation, not just the latest.
- **Tapio is not the only holder.** The model provider receives every prompt and may retain it, and the hosting edge terminates TLS and sees every message in transit.

## Decision

**The server is the only source of a conversation's history.** A client sends a new message and the conversation it belongs to, never earlier turns. The server reads those from its own store and decides how much of them the model sees. A request carrying client-supplied history is rejected. The client renders what the server holds, showing a person's own message optimistically until the server confirms it, and the server's copy wins any disagreement.

**Conversations are encrypted at rest so that destroying a key erases them.** An anonymous conversation is encrypted with a key derived from the session's secret, which only the person's browser holds; the server keeps a hash of the secret, never the secret or the key. Without the browser's cookie the stored conversation is unreadable, to an operator, to someone holding a disk image or backup, or to anyone presenting a legal demand. A registered conversation is encrypted with its own key, which the service holds and destroys when the conversation is deleted or expires. Deletion therefore does not depend on the storage engine overwriting what it removed, though the engine is also configured to.

**Every stored conversation expires automatically, after a short default period.** No conversation is kept indefinitely, and no one has to remember to delete one. Expiry is counted from the last activity, with an absolute maximum from creation that activity cannot extend. The defaults are short, and Finntegrate sets them and their upper bounds as configuration. A registered person can choose a shorter period, or a longer one up to the configured maximum, but never "keep forever". An expired conversation is treated as gone the moment it expires, whether or not the deletion job has run yet.

**Conversations are encrypted in transit on every hop.** Browser to edge, edge to origin, and service to the model provider all use TLS. No hop carries conversation content in plaintext over a network, so the edge and the provider are the only places outside the service that see it, and both are named processors.

**Server-held conversation storage does not go live before its legal basis is settled.** The lawful basis for holding conversation content, anonymous and registered, is decided under [#40](https://github.com/Finntegrate/tapio/issues/40), and a data protection impact assessment is completed, before the beta admits anyone. The model provider and hosting edge are named as processors, and the provider's retention and processing region are settled at the same time.

## Consequences

### Positive

- Forged and inflated history are impossible rather than detected.
- An anonymous conversation at rest is ciphertext that nobody but the person's browser can open. Closing the browser, ending the session, or expiry makes it permanently unreadable, even where deleted bytes linger on disk or in a backup.
- Retention and deletion act in one place, with a guarantee that does not depend on the storage engine.
- Data minimisation holds by default: the service keeps only what a short window of conversation needs, and what it keeps disappears without anyone acting.
- A legal demand for anonymous conversations can yield nothing readable, and the service can say so truthfully.

### Negative

- Every conversation exists on Tapio's infrastructure for its lifetime, which client-held history avoided. Encryption limits what that copy can yield; it does not remove it, and a conversation is readable in the server's memory while a turn runs.
- Registered conversations are readable by someone with access to both the host and the service's secrets. Encryption protects them against disk images and stray backups, not against a compromised running service.
- Losing the browser's cookie loses an anonymous conversation irrecoverably. That is the property working as intended, but it is also a way to lose work.
- A legal-basis decision and an impact assessment now sit on the path to opening the beta.
- Encrypting per session or per conversation is more machinery than encrypting a whole database with one key.
- A registered person working through a permit process that takes longer than the absolute maximum loses the earliest conversations. The interface shows each conversation's expiry so that nothing disappears by surprise.

### Risks

- A serializer that encrypts conversation content can still leave plaintext in places it does not cover, such as checkpoint metadata, logs, or error reports. The specification requires a test that searches the stored bytes for a known message.
- The model provider's retention may exceed Tapio's. If no provider offers zero retention or EU processing at a price the project can carry, the privacy notice has to say how long prompts live there.
- Prompt content passes through the hosting edge in plaintext. Choosing the edge is a privacy decision as well as a resilience one.

## Alternatives considered

### Keep history on the client, unsigned

Rejected. This is the current behaviour, and it lets a client forge earlier turns and inflate input cost.

### Keep history on the client, signed by the server

The server would sign each turn so the client could not forge or reorder them, and would trim the history to its own window so the client could not inflate it. Rejected because it moves the whole transcript over the network on every turn, which collides with the request size bound and slow connections, and because a person who wants to return on another device still needs server storage. It does avoid holding anonymous content at rest, which is why the anonymous design keeps that property another way: by encrypting with a key only the browser holds.

### Server-held history in plaintext, protected by retention alone

Rejected. Retention bounds how long content exists, but a disk image, backup, or legal demand inside the retention window yields everything, and deleted rows can survive in free pages and the write-ahead log.

### One database-wide encryption key

Rejected as the only control. It protects a stolen disk but not a running host, a backup taken with its key, or a legal demand served on the operator, and it cannot erase one conversation without rewriting the database.

## References

- [Specification: conversation history](../specs/conversation-history.md) — the mechanism this decision commits to
- [ADR 0008: Anonymous by default](0008-auth-and-tenancy.md), which owns conversation ownership and principals
- [ADR 0009: Abuse and cost controls](0009-abuse-and-cost-controls.md), which depends on server-held history
- [PRD §5, §7.5–7.6](../PRD.md)
- [#16: Checkpointer](https://github.com/Finntegrate/tapio/issues/16), [#35: Saved conversations](https://github.com/Finntegrate/tapio/issues/35), [#40: GDPR compliance review](https://github.com/Finntegrate/tapio/issues/40)
