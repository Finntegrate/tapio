# ADR 0010: The server holds conversation history, encrypted and kept only briefly

## Status

Accepted

## Date

2026-10-07

## Context

The chat API currently accepts a conversation's earlier turns from the client. A client can therefore forge turns, including answers a guide never gave, and inflate the input the project pays for ([ADR 0009](0009-abuse-and-cost-controls.md)).

Moving history to the server closes both, but reverses a privacy property: conversations that were stored nowhere would now exist on Tapio's infrastructure. Conversations from this population routinely contain special-category data (GDPR Art. 9), and the safest record is the one that does not exist (PRD §5). So the question is also what a disk image, a backup, or a legal demand could yield. Deleting a row does not erase its bytes from an embedded database, and the model provider and hosting edge see conversations too.

## Decision

**The server is the only source of a conversation's history.** A client sends a new message, never earlier turns, and a request that carries them is rejected. The client renders what the server holds, optimistically, and the server's copy wins any disagreement.

**Conversations are encrypted at rest so that destroying a key erases them.** An anonymous conversation's key can be derived only from a secret held by the person's browser, so without that browser it is unreadable to anyone, Finntegrate included. A registered conversation's key is held by the service and destroyed when the conversation is deleted or expires. Erasure does not depend on the storage engine overwriting what it removed.

**Every conversation expires automatically, with short defaults.** Nothing is kept indefinitely, and nothing depends on anyone remembering to delete it. People may choose shorter retention, or longer within a bound Finntegrate sets.

**Conversations are encrypted on every network hop**, so only named processors ever see them outside the service.

**Server-held storage does not go live before its legal basis is settled**: the lawful basis under [#40](https://github.com/Finntegrate/tapio/issues/40), a data protection impact assessment, and the processors' retention and region.

## Consequences

### Positive

- Forged and inflated history become impossible rather than detected.
- An anonymous conversation at rest yields nothing readable to a disk image, a backup, or a legal demand.
- Deletion and expiry hold whatever the storage engine leaves behind.
- Data minimisation is the default, without anyone acting.

### Negative

- Every conversation exists on Tapio's infrastructure for its lifetime, and is readable in memory while a turn runs.
- Registered conversations are readable by someone holding both the host and the service's secrets.
- Losing the browser's state loses an anonymous conversation for good.
- A long process can outlast a registered conversation's maximum retention.
- A legal decision and an impact assessment sit on the path to the beta.

### Risks

- Content can leak around the encryption, through metadata, logs, or error reports.
- The model provider's retention may exceed Tapio's.
- The hosting edge sees traffic in plaintext, so choosing it is a privacy decision.

## Alternatives considered

- **Client-held history, unsigned.** Rejected: forgeable and inflatable.
- **Client-held history, signed by the server.** Rejected: the whole transcript crosses the network every turn, and returning on another device still needs server storage. Its benefit, holding nothing readable at rest, is kept by encrypting anonymous conversations with a browser-held key.
- **Server-held plaintext, protected by retention alone.** Rejected: everything inside the retention window is exposed, and deleted rows can survive on disk.
- **One database-wide key.** Rejected as the only control: it protects a stolen disk, not a running host or a demand on the operator, and cannot erase one conversation.

## References

- [Specification: conversation history](../specs/conversation-history.md)
- [ADR 0008](0008-auth-and-tenancy.md), [ADR 0009](0009-abuse-and-cost-controls.md), [ADR 0011](0011-privacy-and-security-baseline.md)
- [PRD §5, §7.5–7.6](../PRD.md)
- [#16](https://github.com/Finntegrate/tapio/issues/16), [#35](https://github.com/Finntegrate/tapio/issues/35), [#40](https://github.com/Finntegrate/tapio/issues/40)
