# Conversation history — specification

**Status:** Proposed

**Owner:** Finntegrate

**Related architecture:** [ADR 0010](../ADRs/0010-server-held-conversation-history.md), [ADR 0008](../ADRs/0008-auth-and-tenancy.md)

## Problem statement

The server is the only source of a conversation's history ([ADR 0010](../ADRs/0010-server-held-conversation-history.md)). This specification defines how a turn is requested, run, and recorded; how the client renders history it does not own; how stored conversations are encrypted, deleted, and expired; and what the service can and cannot produce from them. Who owns a conversation and how a caller is identified is in [authentication and tenancy](auth-and-tenancy.md).

## Goals

1. A client cannot add, alter, reorder, or inflate any earlier turn.
2. An anonymous conversation at rest is unreadable without the person's browser.
3. Deleting or expiring a conversation makes it unreadable everywhere Tapio holds it, whatever the storage engine leaves on disk.
4. Every conversation expires automatically after a short default period, and content is encrypted at rest and on every network hop.
5. A person sees their message straight away, and a dropped connection never loses an answer the service already paid for.

## Non-goals

- **Holding conversations the person has not been told about.** Retention is stated in the interface before a conversation is long.
- **End-to-end encryption.** The server reads a conversation while running a turn. Encryption here protects data at rest.
- **Choosing the production database.** Storage is embedded first; see [Storage](#storage).

## Turns

### The request

A turn request carries the `thread_id`, the new message, and a client-generated `client_message_id`. Nothing else from the conversation is accepted. A request carrying any history field is rejected with a validation error, not silently ignored, so a client bug is visible rather than masked.

The server loads prior turns from the checkpointer, selects what the model sees (see [What the model sees](#what-the-model-sees)), and runs the turn.

### Lifecycle

A turn is in exactly one state.

| State | Entered when | Persisted |
| --- | --- | --- |
| `accepted` | The request passes validation, ownership, rate limits, and admission ([abuse and cost controls](abuse-and-cost-controls.md)) | An in-progress marker with the server message id; no content |
| `completed` | The answer, including any guardrail resources, is finished | The person's message and the answer, written together |
| `failed` | A model or provider error, or a bound stopping the turn before an answer exists | Nothing beyond removing the marker |

A request that is refused before it is accepted, for example by a rate limit or a full queue, creates no turn.

The person's message and the guide's answer become part of the conversation together. A conversation never contains a message without its answer, so a failed turn leaves no dangling question for later turns to see.

A turn whose guardrail classification matched `crisis` or `legal_sensitive` always ends `completed` with its deterministic resources, even if a bound fires after the match ([abuse and cost controls](abuse-and-cost-controls.md#request-bounds)). Guardrail-intercepted turns are persisted like any other, so the resources are still there when the conversation is reopened, and are protected the same way.

### Disconnects

A turn does not end because the client went away. Once `accepted` it runs to `completed` or `failed` within its bounds, and is persisted. The admission slot is held until the last upstream model call has returned or been aborted, so a disconnect cannot free capacity while spend continues ([abuse and cost controls](abuse-and-cost-controls.md#admission)). A client that reconnects refetches the conversation and sees the answer.

### Duplicate sends

The `client_message_id` exists only to make a retry safe. If a request arrives with a `client_message_id` the server has already seen on that conversation, it returns the existing turn's state or result instead of running the turn again. The id is random, carries no meaning, and is kept only as long as the turn it belongs to.

A conversation runs at most one turn at a time.

### What the model sees

The server builds the model's input from server-held turns only: the most recent turns that fit a history window of 6,000 tokens, counted with the provider's tokenizer. Scripts tokenize unevenly; the window is sized so that the least efficiently tokenized language the guides support still keeps several exchanges, and is configuration.

## The client

The client hydrates from the server and renders optimistically. Its copy is a cache; where it and the server disagree, the server wins.

- On opening a conversation, the client fetches its turns and renders them. An `accepted` turn is shown as in progress.
- On sending, the client shows the person's message immediately as pending. The first stream event acknowledges it with the server message id, and the client marks it sent.
- Streamed answer text is rendered as it arrives and replaced by the persisted answer when the turn completes.
- If the request is refused or the turn fails, the pending message is marked not sent and its text returns to the input for retry, with the same `client_message_id`.
- After a reconnect, or when a stream ends without a completion event, the client refetches the conversation rather than trusting what it rendered.
- A message over the length bound is caught before sending, with a translated explanation that suggests sharing only the relevant passage and leaving out names and case numbers. The server enforces the same bound and returns the same explanation.

## Encryption at rest

Checkpoint content — messages, answers, retrieved passages, guardrail results — is encrypted before it is written, by a checkpoint serializer that uses the key of the conversation's owner. Checkpoint metadata, the ownership record, timestamps, ids, and turn states are not encrypted and must never contain message content.

### Anonymous conversations

An anonymous session's secret is 256 random bits, held only in the browser's cookie. From it the server derives, with HKDF-SHA-256 and distinct context labels:

- a session id, which is what the server stores and looks the session up by, and
- a conversation key, used to encrypt that session's conversations with AES-256-GCM.

Neither the secret nor the key is ever written anywhere. The key exists in server memory only while a request from that browser is being handled. When the cookie is gone, the conversations it encrypted cannot be read by anyone.

### Registered conversations

Each registered conversation has its own random data key, stored in the account store wrapped by a key-encryption key held in the deployment's secret store. Deleting or expiring the conversation deletes its data key.

When an anonymous person signs in and chooses to keep their conversations ([authentication and tenancy](auth-and-tenancy.md#claiming-conversations-on-sign-in)), each one is decrypted with the session key, re-encrypted with a new data key, and its ownership moved to the account, in one transaction per conversation.

## Deletion

Deleting a conversation removes every checkpoint, checkpoint write, and stored blob for its `thread_id`, its ownership record, and, for a registered conversation, its data key. There is no soft delete and no archive. Deletion is idempotent.

Because the key is destroyed, a deleted conversation is unreadable even where its bytes survive. The store is also configured not to leave them: SQLite runs with `secure_delete` on, the write-ahead log is checkpointed and truncated after each expiry run, and the database is vacuumed on a schedule.

A person can end an anonymous session at any time from a control that is always visible. Ending it deletes the session's conversations on the server and clears the browser's state.

## Retention

Every stored conversation has an expiry, set when it is created and moved forward by activity, but never past an absolute maximum counted from creation. Nothing is kept indefinitely, and expiry needs no action from anyone.

| Holder | Default | Absolute maximum | Who can change it |
| --- | --- | --- | --- |
| Anonymous session cookie | The browser session; no stored expiry | — | No one |
| Anonymous conversation | 24 hours after last activity | 7 days after creation | Operators, as configuration |
| Registered conversation | 30 days after last activity | 12 months after creation | The person, per conversation or as their default, choosing 1, 7, 30, or 90 days after last activity; operators set the choices and the maximum |

The defaults are short on purpose: data minimisation is the default, and keeping more is a choice the person makes. There is no "keep forever" choice. Operators can shorten any value or lower the maximum, and a lowered maximum applies to existing conversations at the next expiry run. Raising a default never extends a conversation that already exists.

An expired conversation is treated as nonexistent from the moment it expires: every read checks the expiry, so nothing is served between expiry and deletion. A job runs at least hourly to delete expired conversations and sessions ([Deletion](#deletion)). The interface shows when each conversation will expire. There are no expiry warnings by email, because the service does not keep an address to send them to ([authentication and tenancy](auth-and-tenancy.md#account-data)).

## Encryption in transit

Conversation content crosses a network only over TLS 1.2 or later:

- browser to the hosting edge, with HSTS so a browser never falls back to plaintext,
- the hosting edge to the origin, with the origin's certificate verified by the edge,
- the service to the model provider and to the email processor.

No hop is configured to fall back to plaintext. The edge and the model provider decrypt traffic to do their work, which is why they are listed under [Other holders](#other-holders).

## Storage

Conversations are held in a LangGraph checkpointer ([#16](https://github.com/Finntegrate/tapio/issues/16)) backed by embedded SQLite, consistent with the project having no operating budget for a managed database. In-memory storage is used for local development and tests only. Ownership, sessions, and keys are held in a separate store, behind an interface that does not expose the engine ([authentication and tenancy](auth-and-tenancy.md#storage)).

Embedded storage is single-writer. The deployment runs as one process until a move is warranted.

The checkpoint store is not backed up while it holds only anonymous conversations, whose lifetime is shorter than any useful backup. Once registered conversations exist, backups of the account store, which holds their keys, are kept for at most 7 days, so a deleted registered conversation is unreadable in any backup after that. The privacy notice states both.

## Other holders

Tapio is not the only place a conversation passes through. Each of these is a processor named in the privacy notice under [#40](https://github.com/Finntegrate/tapio/issues/40).

| Holder | What it receives | What bounds it |
| --- | --- | --- |
| Model provider | Every prompt: the history window, retrieved passages, and the new message | The provider's data-processing terms, retention, and processing region |
| Hosting edge | Every request and response in plaintext, because it terminates TLS | The edge's data-processing terms and region ([#44](https://github.com/Finntegrate/tapio/issues/44)) |

## Legal demands

Finntegrate responds to a demand for user data only as the law requires, with legal advice, and produces only what it holds in readable form.

- **Anonymous conversations:** ciphertext and timestamps, which cannot be decrypted without the person's browser. The service has nothing readable to produce.
- **Registered conversations:** readable, but an account can only be found by an email address, which the service holds only as a keyed hash. A demand must name the address.
- **Everything else:** no network addresses, no access codes, and no partner referral lists are kept to produce.

Finntegrate publishes, at least yearly, how many demands it received and how many it complied with.

## Failure modes

| Case | Behaviour |
| --- | --- |
| Request carries history | Rejected with a validation error; no model call |
| Client disconnects mid-turn | The turn completes and is persisted; a refetch shows it |
| Duplicate `client_message_id` | The existing turn is returned; nothing runs again |
| Turn fails | Nothing persisted; the client returns the text to the input |
| Anonymous cookie lost | The conversation is unreadable and expires on the server; the interface says so up front |
| Decryption fails for a registered conversation | The conversation is reported as unavailable and an operator alert is raised; it is never served partially |

## Testing

- History: a turn request carrying client-supplied history is rejected; the model receives only server-held turns, within the configured window.
- Lifecycle: a failed turn persists nothing and is absent from the next turn's model input; a completed turn persists message and answer together.
- Disconnect: closing the stream after acceptance still produces a persisted answer, and the admission slot is not released until the upstream call ends.
- Duplicates: two requests with the same `client_message_id` run one turn.
- Plaintext: after a completed turn containing a distinctive test string, neither the database file nor its write-ahead log contains that string.
- Anonymous key: with the store and every server secret but without the cookie, the conversation cannot be decrypted.
- Deletion: after deleting a conversation and running maintenance, no row for its `thread_id` remains in any checkpointer table, and for a registered conversation its data key is gone.
- Retention: the expiry job removes conversations past their bound and leaves those inside it; a conversation past its expiry is not served even before the job runs; activity never extends a conversation past its absolute maximum; a person cannot choose a period above the configured maximum.
- Transit: the origin refuses plaintext connections, and responses carry HSTS.
- Crisis: a turn that matched `crisis` and then hit a bound is persisted `completed` with its resources.
- Claiming: a claimed conversation is readable with the account's data key and no longer with the session key.

## Delivery

Before the beta admits anyone:

1. The lawful basis for holding conversation content is decided under [#40](https://github.com/Finntegrate/tapio/issues/40), and a data protection impact assessment covering anonymous conversation storage is completed.
2. The model provider's retention and processing region, and the hosting edge's, are settled and in the privacy notice.
3. Server-held, encrypted history replaces the client-supplied `history` field in the chat API, with the client hydration above ([#16](https://github.com/Finntegrate/tapio/issues/16)).

Registered conversations follow with accounts ([#31](https://github.com/Finntegrate/tapio/issues/31), [#35](https://github.com/Finntegrate/tapio/issues/35)).

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Lawful basis for holding conversation content, and the impact assessment | Privacy and data ([#40](https://github.com/Finntegrate/tapio/issues/40)) | Yes, before the beta opens |
| Which model provider offers zero data retention or EU processing within the budget, and if none, what the privacy notice says | Engineering, privacy | Yes, before the beta opens |
| Where the hosting edge processes traffic, and whether that is a third-country transfer | Engineering ([#44](https://github.com/Finntegrate/tapio/issues/44)) | Yes, before the beta opens |
| Are a 30-day default and a 12-month maximum right for registered conversations, given how long permit processes take | Product and privacy | No; configuration |
| Whether a 6,000-token window is enough for multi-guide conversations in every supported script | Product and engineering | No; configuration |
