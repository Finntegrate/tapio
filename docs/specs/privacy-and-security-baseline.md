# Privacy and security baseline — specification

**Status:** Accepted, not yet implemented

**Owner:** Finntegrate

**Related architecture:** [ADR 0011](../ADRs/0011-privacy-and-security-baseline.md), [ADR 0008](../ADRs/0008-auth-and-tenancy.md), [ADR 0009](../ADRs/0009-abuse-and-cost-controls.md), [ADR 0010](../ADRs/0010-server-held-conversation-history.md)

## Problem statement

Tapio's privacy and security controls are specified across [authentication and tenancy](auth-and-tenancy.md), [abuse and cost controls](abuse-and-cost-controls.md), and [conversation history](conversation-history.md). This specification adds the controls that cut across all of them — purpose limitation, observability, transparency, data subject rights, the language model's privileges, operator access, and breach response — and maps every principle Tapio commits to onto the controls that meet it and the tests that verify them. The decision is in [ADR 0011](../ADRs/0011-privacy-and-security-baseline.md); this document is the mechanism and the evidence.

## Goals

1. Every principle in the table below has at least one control and at least one test.
2. Every data item Tapio holds has a stated purpose, retention, and location.
3. No conversation content leaves the service except to the processors that answer it.
4. A prompt injection cannot reach anything beyond the attacker's own conversation.

## Non-goals

- **Proving which user did what.** Non-repudiation applies to operators only.
- **Multi-factor authentication for users.** A user account guards one person's conversations and is reached by inbox control; adding factors would add identity data. Operators are covered below.
- **Answer accuracy.** Whether an answer is correct is a matter of grounding and guardrails ([PRD §7.4](../PRD.md)), not of data accuracy.

## Principles

| Principle | Controls | Specified in | Verified by |
| --- | --- | --- | --- |
| Lawfulness | Lawful basis decided per processing purpose before it starts; storage gated on it | [#40](https://github.com/Finntegrate/tapio/issues/40); [conversation history](conversation-history.md#delivery) | The impact assessment; delivery checklist |
| Fairness | No feature depends on identity, status, or language; limits sized for shared networks; emergency line on every refusal | [abuse and cost controls](abuse-and-cost-controls.md#emergency-line) | Shared-network and emergency-line tests |
| Transparency | Notice before the first message, in the person's language; expiry shown per conversation | [Transparency](#transparency) | Notice test |
| Purpose limitation | Content used only to answer; no training, evaluation, or analytics; provider no-training terms | [Purpose limitation](#purpose-limitation) | Purposes register review; provider terms check |
| Data minimisation | No identifying fields; email kept as a keyed hash only; network addresses hashed in memory; content-free metrics | [auth and tenancy](auth-and-tenancy.md#account-data); [abuse and cost controls](abuse-and-cost-controls.md#rate-limits) | No-email, no-address, no-content tests |
| Accuracy | Little personal data to be wrong; affiliation changeable and removable; conversations deletable, never edited by the service | [auth and tenancy](auth-and-tenancy.md#partner-affiliation) | Affiliation tests |
| Storage limitation | Automatic expiry with short defaults and absolute maximums; idle accounts deleted; bounded backups | [conversation history](conversation-history.md#retention) | Retention tests |
| Integrity and confidentiality | Ownership on every request; encryption at rest with browser-held keys; TLS on every hop; server-held history | [conversation history](conversation-history.md#encryption-at-rest); [auth and tenancy](auth-and-tenancy.md#conversation-ownership) | Ownership, plaintext-scan, and history tests |
| Availability | Edge protection; turn-start rate; per-code shares; provider ceiling | [abuse and cost controls](abuse-and-cost-controls.md) | Admission and fairness tests |
| Accountability | This table; the purposes register; operator audit log; breach plan; tests in CI | [Accountability](#accountability) | CI gate; yearly review |
| Defence in depth | Edge, request bounds, turn-start rate, provider ceiling; encryption plus key destruction plus `secure_delete` | [abuse and cost controls](abuse-and-cost-controls.md#threats-and-the-controls-that-answer-them) | Each layer's tests independently |
| Least privilege | Model reaches only the caller's conversation and read-only tools; operators by named grant | [The language model](#the-language-model); [Operators](#operators) | Tool-registry and isolation tests |
| Separation of duties | Partner administrators see aggregates, never conversations; operators have no conversation reader | [auth and tenancy](auth-and-tenancy.md#principals) | Role tests |
| Fail-safe defaults | Unreadable store or kill-switch source closes the service; decryption failure serves nothing | [abuse and cost controls](abuse-and-cost-controls.md#failure-modes) | Closed-state tests |
| Secure defaults | Affiliation off; challenges off; shortest retention; browser-session cookies; tracing off | All three specifications | Default-configuration test |
| Small attack surface | No social login, passwords, or paid tools; one origin; no third-party scripts | [auth and tenancy](auth-and-tenancy.md#web-security) | CSP test |
| Input validation and output encoding | Size bounds; client history rejected; model output rendered as text | [abuse and cost controls](abuse-and-cost-controls.md#request-bounds); [The language model](#the-language-model) | Bounds and rendering tests |
| Strong authentication | Browser-bound sign-in codes for users; phishing-resistant MFA for operators | [auth and tenancy](auth-and-tenancy.md#sign-in); [Operators](#operators) | Sign-in binding test |
| Non-repudiation | Operators only, through the audit log | [Operators](#operators) | Audit log test |
| Continuous security testing | Privacy tests, dependency and secret scanning, and static analysis on every pull request | [Accountability](#accountability) | Required CI checks |

A change that weakens a control updates this table in the same pull request.

## Purposes register

Every data item Tapio holds. An item not listed here may not be stored.

| Item | Purpose | Retention | Location |
| --- | --- | --- | --- |
| Anonymous session id | Recognize a returning browser; own its conversations | Session lifetime, at most 7 days | Identity store |
| Conversation content | Answer the person who wrote it | [Retention](conversation-history.md#retention) | Checkpoint store, encrypted |
| Conversation data key | Decrypt a registered conversation | Until the conversation is deleted or expires | Identity store, wrapped |
| Email hash | Find an account when its address is typed | Until the account is deleted, at most 180 days after last sign-in | Identity store |
| Pending sign-in | Complete one sign-in in one browser | 10 minutes | Identity store |
| Registered session | Keep a person signed in | 7 days idle, 30 days absolute | Identity store |
| Partner affiliation | Count the person in the partner's aggregates | Until removed, or with its session or account | Identity store |
| Access code record and counters | Admit sessions and limit a code | Until the code is retired | Identity store |
| Network bucket | Limit attempts and turns from one source | At most 24 hours | Memory only |
| Operational metrics | Run the service and size its limits | 90 days | Metrics store; no content or identity |
| Operator audit log | Hold operators accountable | 12 months | Append-only log |
| Prompts at the model provider | Generate the answer | The bound in the provider's terms, recorded here when chosen | Provider |
| Traffic at the hosting edge | Deliver and protect the service | The bound in the edge's terms, recorded here when chosen | Edge |
| Sign-in mail at the email processor | Deliver one code | The bound in the processor's terms, recorded here when chosen | Email processor |

A processor's row is complete only when it states a number of days, or "none" for zero retention, taken from that processor's signed terms, and the transparency notice states the same bound. The beta does not open with a model provider or edge row incomplete, and accounts do not ship with the email processor's row incomplete.

## Purpose limitation

- Conversation content is read by the service only to run a turn, render the conversation to its owner, claim it into an account, or export it to its owner.
- Content is never used to train or fine-tune a model, to build or extend an evaluation set, for analytics or product research, or for debugging. Evaluation uses synthetic and volunteered examples only.
- A model provider is used only under terms that forbid training on Tapio's prompts. Those terms are recorded with the provider choice and checked whenever the provider publishes new terms.
- A new purpose for any item in the register needs its own ADR and lawful basis before any data is touched.

## Observability

- Logs, metrics, traces, and error reports never contain message content, an email address or its hash, an access code, a sign-in code, a session secret, or a network address. Errors are logged by type and location, not by the values involved.
- Third-party tracing of model calls is off. At startup the service refuses to run if `LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` is enabled, or if a tracing API key or endpoint is configured.
- No error-reporting or analytics service receives request or response bodies. Any such service added later is configured to drop them before sending, and is listed as a processor.
- Tracing for operations, when needed, records timings, token counts, and outcomes only, and stays inside the deployment ([#37](https://github.com/Finntegrate/tapio/issues/37), [#38](https://github.com/Finntegrate/tapio/issues/38)).

## Transparency

Before the first message, the interface shows a short notice in the person's language. It says, in plain terms:

- that Tapio is not an official service and is not a substitute for legal advice,
- what is kept, for how long, and that an anonymous conversation is unreadable once the browser session ends,
- that the model provider and hosting provider process messages to answer them, and where,
- not to share names, case numbers, or other identifying details,
- how to delete a conversation and end the session.

The full privacy notice is one step away and lists every item in the [purposes register](#purposes-register), every processor, the lawful basis for each purpose, and how to contact Finntegrate. When the notice changes in substance, it is shown again before the next message.

## Data subject rights

| Right | Registered person | Anonymous person |
| --- | --- | --- |
| Access (Art. 15) | Sees every conversation in the interface | Sees the session's conversations in the interface |
| Portability (Art. 20) | Downloads all conversations as a structured file | Can copy a conversation from the interface |
| Erasure (Art. 17) | Deletes any conversation or the whole account | Deletes any conversation or ends the session |
| Rectification (Art. 16) | Changes or removes affiliation; conversations are a record of what was said and are deleted, not edited | Same |
| Objection and restriction (Art. 18, 21) | Removes affiliation; deletes data | Same |

Tapio does not identify an anonymous person in order to answer a request (Art. 11). The privacy notice says that the rights above are exercised in the interface, and that Finntegrate cannot act on a request it cannot tie to a session or a signed-in account.

## The language model

The model is treated as untrusted. Its input can contain instructions from users and from crawled pages.

- A turn's graph is given only the caller's own conversation, loaded by the server. No tool accepts a `thread_id`, session, or account as an argument.
- Registered tools are read-only and free during the beta ([#17](https://github.com/Finntegrate/tapio/issues/17)). No tool holds a handle to the identity or checkpoint store, the secret store, or the operator command.
- Retrieved passages and user messages are placed in the prompt in delimited sections, separate from system instructions. Delimiters help the model tell the sections apart; they do not stop it following instructions inside them, so no control in this specification relies on them. Isolation is enforced by what the server loads and what the tools can reach.
- Model output is rendered in the browser as text, or as a restricted Markdown subset with raw HTML disabled and links limited to `https` URLs. Nothing from the model is inserted into the page as HTML.

## Operators

- Access to the production host, the secret store, the hosting and provider consoles, and the operator command requires a personal account and phishing-resistant multi-factor authentication (a hardware key or passkey). There are no shared credentials.
- Secrets are readable only by the running service and the named operators who need them.
- Every operator action — issuing or stopping a code, granting or revoking partner administration, opening or closing the service, rotating a key — is written to an append-only audit log with the operator, action, target, and time, never with conversation content or an email address. The log is reviewed monthly.

## Breach response

A written plan, kept with the operator documentation, names an incident owner and a deputy and covers:

1. **Contain:** close the service if needed, stop affected codes, revoke sessions, and rotate affected keys ([auth and tenancy](auth-and-tenancy.md#keys)).
2. **Assess:** what was reachable, using the purposes register. Anonymous conversation content is unreadable without the browser key, which bounds most assessments.
3. **Notify:** the Finnish data protection authority within 72 hours where Art. 33 requires it.
4. **Inform:** affected people where Art. 34 requires it. No one can be contacted directly, because no address is kept, so Tapio uses public communication as Art. 34(3)(c) allows, through every channel that can reach them:
   - a notice shown inside the service to every session and account on its next visit, before the first message, until the longest retention period affected has passed,
   - a notice on the service's front page for the same period,
   - every partner whose codes admitted affected sessions, asked to pass a prepared, translated message through its own channels to the people it referred,
   - a statement to the data protection authority of which channels were used and why direct contact was impossible.

   The incident record notes which channels were used and what reach each had (in-service notices shown, partners who confirmed forwarding), and the plan accepts that people who neither return nor stay in contact with a partner cannot be reached. That limit follows from keeping no contact details, and is stated in the privacy notice in advance.
5. **Learn:** record the incident and update this specification and its tests.

## Accountability

- The principles table and purposes register are the basis of the record of processing activities (Art. 30) and the impact assessment. Both are reviewed at least yearly and whenever the register changes.
- The privacy tests in each specification, dependency vulnerability scanning, secret scanning, and static analysis run on every pull request, and a failure blocks the merge.

## Testing

- Observability: the service refuses to start with tracing enabled; a full admission, sign-in, and chat flow produces no log line, metric, or error report containing a test message, email address, access code, sign-in code, session secret, or network address.
- Language model: no registered tool accepts a conversation, session, or account identifier; a prompt instructing the model to read another conversation has no means to do so; model output containing HTML or script is displayed as text.
- Transparency: the notice is shown before the first message, in the selected language, and again after a substantive change.
- Rights: a registered export contains every conversation the account owns and nothing else.
- Register: a test lists the tables and columns in each store and fails if one is not covered by the purposes register.
- Operators: every operator command writes an audit entry, and none contains an email address or conversation content.
- Defaults: a deployment started with no configuration has affiliation off, challenges off, tracing off, and the shortest retention.

## Delivery

Before the beta admits anyone: the lawful basis for each processing purpose ([#40](https://github.com/Finntegrate/tapio/issues/40)) and a completed data protection impact assessment ([conversation history](conversation-history.md#delivery)), processor retention bounds recorded in the purposes register and the notice, purpose limitation and the provider's no-training terms, the observability rules and the tracing check, the transparency notice, the language-model restrictions, operator authentication and the audit log, the breach plan, and the CI gate. Export ships with registered accounts.

## Open questions

| Question | Owner | Blocking? |
| --- | --- | --- |
| Who is the incident owner and deputy, and is a Data Protection Officer required | Finntegrate ([#40](https://github.com/Finntegrate/tapio/issues/40)) | Yes, before the beta opens |
| Which provider terms forbid training on prompts, and how are changes to them noticed | Engineering, privacy | Yes, before the beta opens |
| How evaluation will measure answer quality without real conversations | Product and engineering | No |
