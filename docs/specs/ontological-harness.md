# Ontological harness for the guide network

**Status:** Proposal, not yet reviewed

**Milestone:** Proposed for 2.1.0, ahead of further guide development

**Owner:** Finntegrate

**Related:** [ADR 0007: constrain guide answers with an ontological harness](../ADRs/0007-ontological-harness.md), [PRD §7.2 proactive guidance](../PRD.md#72-proactive-guidance), [PRD §7.3 grounded answers and sources](../PRD.md#73-grounded-answers-and-sources), [PRD §6 the guide network](../PRD.md#6-the-guide-network), [guardrails policy](guardrails.md), [guide network grounding sources](../research/guide-network-grounding-sources.md), issues [#15](https://github.com/Finntegrate/tapio/issues/15), [#26](https://github.com/Finntegrate/tapio/issues/26), [#27](https://github.com/Finntegrate/tapio/issues/27), [#33](https://github.com/Finntegrate/tapio/issues/33), [#119](https://github.com/Finntegrate/tapio/issues/119)

---

## 1. Summary

Tapio's guides currently produce free prose. Retrieval gives that prose grounding, and the system prompt asks for citations, but nothing in the pipeline can *check* whether a given answer named a real permit, attributed it to the right authority, cited a source that was actually retrieved, or stayed inside the answering guide's remit. Those are all properties a machine can verify, and today none of them are verified.

This proposes a deterministic layer around the existing LangGraph flow. The central move is small and worth stating on its own, because everything else follows from it:

> **The model keeps the words. The harness owns the commitments.**

A guide turn contains two different kinds of output. One is language: plain, warm, in the user's own language, calibrated to someone who is confused and under time pressure. That is what an LLM is genuinely good at and we should not constrain it. The other is a set of factual commitments: *this permit type*, *this authority*, *this next step*, *this source*, *this guide answered*. Those are not language. They are references into a finite, knowable set of entities, and a model that emits them as free text will occasionally emit one that does not exist.

So we separate them. The model emits a small structured **answer plan** whose entity slots must resolve against a published **term register**, and whose citation slots must resolve against the chunks actually retrieved this turn. The prose rides inside that plan and stays unconstrained. A plan that fails validation gets one targeted repair attempt, then degrades to an honest fallback.

This is an information retrieval and information science problem, not a formal verification one. The cut taken here reflects that: closed-world vocabulary gate, deterministic entity resolution, shape validation, and a repair loop. Section 4 says what is deliberately left out. Section 7 covers a second output the register produces almost for free, which is a time-indexed record of how the Finnish immigration system itself changes. Section 8 covers what the harness makes possible at the interface, which is showing the user what Tapio currently believes about their situation and letting them correct it.

## 2. What this fixes that better retrieval does not

Four failure modes are structural. More documents, better chunking, and a bigger model reduce their frequency but cannot eliminate them, because nothing in a RAG pipeline is capable of noticing them.

### 2.1 Entities that do not exist, or no longer do

A model can name a permit category, a benefit, a form, or an office that is plausible and wrong. The version of this that matters most for Tapio is not invention, it is **staleness**, and it is a problem the corpus makes worse rather than better.

Finnish administrative structure has been reorganized repeatedly and recently. The grounding-sources research already documented three instances: TE Offices were dissolved on 1 January 2025 and their services moved to 45 municipal employment areas; ELY Centres were renamed and reorganized as Elinvoimakeskus during 2025 and 2026; health and social service organization moved to 21 wellbeing services counties plus Helsinki in 2023. The crawled corpus contains pages written before each of those changes, and PRD §5 commits to refreshing that corpus on a bounded schedule rather than in real time. Retrieval will keep surfacing stale entities because the stale pages are genuinely in the corpus and genuinely relevant.

A term register fixes this at the layer where it is fixable. It is small enough for a person to keep current, and superseded entities stay in it with a pointer to their successor rather than being deleted. "TE Office" then stops being an unrecognized string and becomes a *repairable* one: the gate rejects the assertion and hands the model the replacement. That is a correction the corpus cannot make on its own.

### 2.2 Terminology that drifts between guides and languages

Issue #119 already describes this: guides independently translate "residence permit" and the renderings diverge. The fix proposed there is a lookup tool, which is right, but the artifact it needs is the same artifact this harness needs. A SKOS concept with one `prefLabel` per language *is* the glossary entry, and making it the thing the validator checks against means it cannot silently fall out of use. A glossary that guides may consult drifts. A register that guides must resolve against does not.

### 2.3 Scope leakage across guides

PRD §6 makes expertise visibility a product principle and ADR 0005 requires a documented scope plus routing tests before a new guide launches. Seven more guides are planned. Today scope lives in two places: a hand-written `out_of_scope` sentence in `backend/app/agents/definitions.py`, and a hand-maintained `activation_terms` tuple that the keyword scorer in `agents/router.py` matches literally against a case-folded message.

That approach has a ceiling. The activation terms are English-only in a product with no monolingual assumption about its users, which is the same objection the guardrails policy already raised against the old keyword-based classifier. And nothing checks the boundary after the fact: if Otso answers a Kela question, the system does not notice.

If a guide's scope is a set of concepts rather than a list of strings, three things fall out at once. Routing works in any language the register has labels for. Scope becomes checkable after generation, not just suggestive before it. And the routing tests ADR 0005 requires can be generated from the register rather than written by hand for each of the seven planned guides.

This is the specific reason to do this work before building more guides rather than after. Seven guides built on hand-maintained English keyword lists is seven guides to retrofit.

### 2.4 Citations that were never retrieved

PRD §7.3 requires substantive answers to cite their sources, and §10 sets a 90% target for source availability. Credit where it is due: the `citation` SSE event in `backend/app/streaming.py` is already built deterministically from `retrieved_docs`, so the citation *panel* cannot contain an invented source. That is the right design and this proposal does not change it.

The gap is the prose. The system prompt asks the model to cite the source URL when one appears in the context, and nothing checks what it does with that instruction. A model can put a plausible migri.fi URL inline that was not in this turn's retrieval set, and more importantly, nothing connects an individual claim to the specific chunk that supports it. "At least one source was retrieved for this turn" and "this sentence is supported by that source" are different properties, and only the first is currently true by construction.

### 2.5 The case that makes the harness worth building: proactive guidance

PRD §7.2 is the feature with no open issue and the largest exposure. A guide that only answers the literal question can be wrong. A guide that volunteers unrequested next steps can be wrong in a direction the user had no reason to check, which for someone acting on a residence permit deadline is a materially different kind of harm.

Free generation is the wrong mechanism for it. A process graph is the right one. If the register holds processes with `prerequisite`, `nextStep`, `requiredDocument`, and `handledBy` edges, then a proactive suggestion is a **traversal result**, not a generation. The model's job shrinks to phrasing a step that the graph already asserted, in the user's language, with the citation the graph already carries. The failure mode flips from "the model invented a step" to "we have no step in the graph for this situation," and the second one is safe: the guide says nothing extra, which is what PRD §8 already asks for.

This also gives a partial answer to the open question in PRD §11 about whether useful anticipation can survive the no-PII posture. Situational context expressed as three concept IRIs (permit type, process stage, applicant category) is not personally identifying, does not need to persist past the turn, and is enough to traverse the graph. That is a narrower thing to hold than free-text situational context, and it is worth testing whether it is sufficient before concluding that proactive guidance requires something the privacy posture rules out.

## 3. Architecture

### 3.1 Current flow

Guardrail classification runs in `backend/app/streaming.py`, ahead of the graph. The compiled graph in `graph/orchestrator_graph.py` is linear:

```text
START -> route -> retrieve -> generate -> END
```

### 3.2 Proposed flow

`route` and `retrieve` are unchanged. The existing `generate` node splits: the commitments it used to make implicitly in prose become `plan`, the prose itself becomes `render`, and `validate` sits between the two with `repair` and `degrade` on the failure edge.

```text
(guardrail classification, existing, in streaming.py)
  `-- matches --> guardrail response, no retrieval --> END
  `-- no match --> the graph below

START
  -> route         (existing scorer, plus concept-set scoring)
  -> retrieve      (existing)
  -> plan          (constrained generation of the answer plan, resolving concepts)
  -> validate      (vocabulary, citation, scope, type, currency)
       |-- conforms --> render (stream prose) --> END
       `-- violates --> repair (bounded, one attempt) --> validate
                            `-- still violates --> degrade --> END
```

The guardrail layer keeps its current behavior exactly: it runs before the graph, and a crisis, legal-sensitive, or out-of-scope match short-circuits the turn so nothing is retrieved and none of the nodes below execute. The harness wraps the whole route-through-degrade flow and does not move, weaken, or depend on that check. If the guardrail checks are later folded into the graph as an input-classifier node, as the guardrails policy anticipates, they belong ahead of `route`.

**Resolution is the model's job, validation is the harness's.** Mapping what a person wrote to a concept is a language problem: Finnish is heavily inflected, Swedish compounds, and a real question mixes languages and misspells things. The model already reads all of that, so it names the concept and the harness checks the name. `plan` emits IRIs; `validate` decides whether they exist, are in scope, and are in force.

This is the division the whole design rests on, and it is worth stating negatively too. A deterministic matcher over the register's labels would be a bigger, better-curated version of the keyword list §2.3 exists to replace: to survive contact with `oleskeluluvan` it would need stems and inflected forms for every term in every language served, which is a combinatorial lexicon to hand-maintain and a linguist's job to get right. Nothing in the harness's guarantees needs it. A model that proposes a concept that does not exist is caught by G1 exactly as a model that proposes one it hallucinated, because closed-world membership is a set operation over identifiers and does not care how the identifier was arrived at.

What the register therefore is: an authority over which entities may be asserted, and a record of when each was in force. What it is not: a lexicon for matching strings.

The graph itself is unchanged in kind. Resolved concepts and `situation` live in the LangGraph state exactly as they would have; what differs is which node writes them. The model mutates that state inside `plan`, the deterministic nodes read it, and `validate` decides whether what was written may stand. Keeping it in the state rather than recomputing it per turn is also what lets a correction from the user (§8.3) or a concept resolved on an earlier turn feed forward as an IRI, instead of being re-derived from text every time.

**plan** replaces the free-prose generation call with a schema-constrained one. Critically, this needs no new dependency: `guardrails/llm_classifier.py` already binds Pydantic schemas through `BaseChatModel.with_structured_output` on the shared model that `app.services.chat_model.build_chat_model` constructs. That rung of the ladder is already in the codebase and already load-bearing for safety. We are extending an established pattern, not introducing one.

The provider abstraction added in #143 helps here rather than complicating it. Because the pipeline depends on `BaseChatModel` rather than a specific client, `with_structured_output` is available uniformly across the configured providers, so the plan node does not become provider-specific. What does differ is the mechanism underneath: Ollama constrains generation with a JSON-schema grammar, while the hosted providers use their own structured-output paths. The guarantee is comparable, the failure behavior on an awkward schema is not, which is one more reason to keep the plan schema flat (§9.3) and to validate it against whichever provider a deployment actually uses rather than only against the default.

**validate** is pure Python plus pySHACL, no model call, and therefore deterministic and fast.

**repair** gets exactly one attempt. See §5.

### 3.3 The answer plan

Sketched as LinkML, which compiles to the Pydantic classes the codebase already uses, the JSON Schema that constrains the Ollama call, and the SHACL shapes the validator runs. One source, three generated artifacts, no drift between them.

```yaml
id: https://tapio.finntegrate.org/schema/answer-plan
name: tapio-answer-plan
prefixes:
  linkml: https://w3id.org/linkml/
  tapio: https://tapio.finntegrate.org/schema/
default_prefix: tapio
imports: [linkml:types]

classes:
  AnswerPlan:
    description: The checkable commitments behind one guide turn.
    attributes:
      answering_guide: { range: GuideId, required: true }
      situation:       { range: SituationItem, multivalued: true }
      claims:          { range: Claim, multivalued: true }
      next_steps:      { range: NextStep, multivalued: true }
      handoff:         { range: Handoff }
      unsupported:
        description: Parts of the question no retrieved source covered.
        range: string
        multivalued: true

  SituationItem:
    description: One thing Tapio is currently taking to be true of the asker's
      situation, and where that came from. Surfaced to the user (§8).
    attributes:
      concept: { range: uriorcurie, required: true }
      role:
        description: What this item is, e.g. permit type, process stage,
          applicant category.
        range: SituationRole
        required: true
      basis:   { range: Basis, required: true }
      evidence:
        description: Required when basis is stated. Identifies the span of the
          person's own message this was taken from, as a turn index plus
          character offsets. Absent for inferred and default, which have no
          span to point at. Checked by G7.
        range: MessageSpan

  MessageSpan:
    attributes:
      turn:  { range: integer, required: true }
      start: { range: integer, required: true }
      end:   { range: integer, required: true }

  Claim:
    attributes:
      text:
        description: Prose in the user's language. Carries no commitment the
          structured slots below do not also carry. See G6.
        range: string
        required: true
      about:
        description: Concepts this claim is about. Must resolve in the register.
        range: uriorcurie
        multivalued: true
        required: true
      authority:
        description: The responsible body, when the claim names one.
        range: uriorcurie
      cites:
        description: Chunk ids from THIS turn's retrieval set. Closed set.
        range: string
        multivalued: true
        required: true
      as_of:
        description: The date this claim describes. Defaults to the turn date
          when absent. Set to a past date for a claim about how things were.
        range: date
      historical:
        description: True when the claim deliberately describes a superseded
          state of affairs, e.g. answering "what applied when I arrived in
          2023". Requires as_of. Changes how G5 reads validity.
        range: boolean
        ifabsent: 'false'

  NextStep:
    attributes:
      step:      { range: uriorcurie, required: true }
      authority: { range: uriorcurie }
      because:   { range: uriorcurie }
      cites:     { range: string, multivalued: true, required: true }

  Handoff:
    attributes:
      to_guide: { range: GuideId, required: true }
      reason:   { range: string, required: true }

enums:
  GuideId:
    permissible_values: { tapio:, ilmarinen:, sampo:, rauni:, otso: }
  Basis:
    description: How Tapio came to hold this. Drives how it is displayed.
    permissible_values:
      stated:   { description: The person said so in this conversation. }
      inferred: { description: Derived from what they said. }
      default:  { description: A general assumption, nothing specific was said. }
```

Note `unsupported`. PRD §7.3 already commits to saying so when no reliable source was found. Giving the model a named slot for "this part of the question was not covered" makes that behavior structural rather than dependent on the model volunteering a hedge, and it produces a countable signal for the eval work in #27.

Note also `situation`. It is the state §8 surfaces, it is what the process graph traverses from, and it costs nothing extra because the pipeline has to hold it anyway.

### 3.4 The gates

Seven checks, ordered cheapest first, all deterministic.

| Gate | Checks | Mechanism | Failure is |
| --- | --- | --- | --- |
| G1 Vocabulary | Every IRI in `about`, `authority`, `step`, `because`, `concept` exists in the register | Set membership against the loaded register | Repairable |
| G2 Citation | Every `cites` value is a chunk id from this turn's retrieval set; every `Claim` has at least one | Set membership against graph state | Repairable |
| G3 Scope | Every concept is within the answering guide's scope, or within `handoff.to_guide`'s scope | SHACL, one shape per guide, generated from the register | Repairable |
| G4 Type soundness | An `authority` is an organization, a `step` is a process, a benefit is not attributed to Migri | SHACL `sh:class` and path constraints | Repairable |
| G5 Currency | Every concept is in force at the claim's reference date, per the rules below | Date comparison plus `supersededBy` lookup | Repairable, often auto-repairable |
| G6 Prose binding | `Claim.text` names no entity or URL absent from that claim's validated slots | Label and URL scan against the claim's allowed set | Repairable |
| G7 Stated evidence | Every `SituationItem` with `basis: stated` carries an `evidence` span resolving to text the person actually wrote | Offset lookup against conversation history | Not repairable by the model; demote to `inferred` |

G1, G2, G6, and G7 are plain Python operations and belong in Python, not SHACL. G2 and G6 in particular are parameterized by the turn, so expressing them as SHACL would mean generating a shape per request for no benefit. G3, G4, and G5 are static per guide and per register version, so they compile once at startup and belong in SHACL where they are declarative and reviewable.

**G3 and handoffs.** A `handoff` is a narrow licence, not a blanket one. A concept outside the answering guide's scope is permitted only when a handoff is present *and* that concept falls within `handoff.to_guide`'s own scope set. Otherwise emitting a handoff would let a guide assert anything at all, which is the opposite of what the gate is for: Otso handing off to Rauni may say that housing benefit is Kela's, not that a residence permit works a particular way. The handoff's `reason` and target guide are unaffected and still shown to the user; only what may be asserted alongside it is bounded.

**G5 and reference dates.** A claim's reference date is `as_of` when present and the turn date otherwise. An ordinary claim (`historical: false`) must name only concepts in force at that date, so an entity whose `validUntil` has passed fails and is auto-repaired through `supersededBy`. A claim marked `historical: true` must carry an `as_of`, and its concepts are checked for being in force *at that date* rather than today, which is what lets a guide correctly answer "what applied when I arrived in 2023" without the gate rewriting the answer into the present. A `historical` claim with no `as_of`, or one whose concepts were not yet in force at its `as_of`, fails. This is why the register's `validFrom` matters operationally and not only as an archival nicety (§7.4).

G5 is the one that earns its keep in this domain specifically. When a present-tense claim asserts `org:te-office`, the register knows that entity has a `validUntil` of 2025-01-01 and a `supersededBy` pointing at `org:municipal-employment-area`. That is enough to rewrite the assertion deterministically and tell the model what changed, without another generation round.

**G6 and why prose needs a gate at all.** The premise of this design is that the model keeps the words while the harness owns the commitments, but prose can smuggle a commitment past every structural check: a claim whose slots are impeccable can still contain a sentence naming a permit that does not exist, or an invented URL. The primary defense is rendering rather than checking. Names of concepts, authorities, and sources are emitted into the prose from the validated slots, through the register's labels in the user's language, rather than written freehand by the model. G6 is the backstop for what slips through: a scan of `Claim.text` for register labels and for URLs, rejecting any that do not appear in that claim's own `about`, `authority`, or `cites`. It is deliberately narrow. It matches known labels and URL shapes, not meaning, and it will not catch a wrong statement built entirely from correct names. That is §9.5's limit, restated: the harness bounds what an answer can refer to, not whether what it says about those things is true.

**G7 and the panel's honesty.** A `SituationItem` with `basis: stated` asserts that the person said something, and §8.2 displays it differently on that basis. The claim is only as good as its evidence, so `stated` requires an `evidence` span that resolves to text in the conversation history. A model that promotes its own guess to "you told me" makes the panel in §8 lie, which is worse than having no panel. Failure here is not sent back for repair, because a model that has already fabricated an attribution is the wrong party to ask for a better one: the item is silently demoted to `inferred`, where the interface presents it as an assumption open to correction, and the demotion is logged.

## 4. What we are leaving out, and why

The research document that prompted this is written for regulated enterprise automation: systems that execute transactions, mutate records, and must defend those actions under SOX or HIPAA. Tapio executes nothing, mutates nothing, and holds no case data by design. Several components solve problems Tapio does not have, and one of them is actively harmful here.

| Component | Its enterprise purpose | Verdict for Tapio |
| --- | --- | --- |
| OWL 2 DL reasoning (HermiT, whelk-rs) | TBox satisfiability over expressive description logics | **Cut.** The domain's real structure is subsumption and a handful of typed relations. SKOS `broader`/`narrower` plus RDFS covers it. Reintroduce only if a concrete inference is needed that SHACL cannot express. |
| Gate 2, policy engine (OPA, Cedar) | Authorization, delegation limits, separation of duties | **Cut.** There is no actor, no privilege, and no write. The nearest analogue is guide scope, which is a semantic question and belongs in G3. |
| Signed evidence bundles (Ed25519) | Non-repudiation under audit | **Cut, and it is worth saying why loudly.** A cryptographically signed, per-turn record binding a prompt to an answer is an accumulating artifact about a person asking about asylum or deportation. PRD §5 treats a data exposure for those users as a physical-safety risk, not a compliance incident. Building tamper-evident records of their questions runs directly against that. See §6 for what to build instead. |
| Separate constrained-decoding runtime (llama.cpp GBNF, Outlines) | Grammar-constrained generation | **Already have it.** Ollama's JSON-schema mode, used today in `llm_classifier.py`, is this. No new dependency. |
| SPIRES model-driven extraction | Grounding entities out of arbitrary documents | **Adapted.** The model names concepts, as SPIRES does, but against a closed register rather than an open ontology, and the result is validated by set membership rather than trusted. |
| Ontology Access Kit | Cross-ontology term mapping | **Defer.** The register records its own alignments (`exactMatch`, `closeMatch`) as data. Revisit if mapping to external vocabularies becomes routine. |

The honest summary: about half of that architecture applies here, and the half that applies is the half that is cheap.

## 5. Repair and degradation

A validation failure produces a machine-readable report naming the failing node, the failing path, and the constraint that failed. That is enough to build a targeted repair prompt: the specific bad value, the reason it is bad, and the valid alternatives where the register knows them. The model fixes that slot and leaves the rest of the plan alone.

Three rules keep this bounded.

**One attempt, never a loop.** An open-ended retry loop is the failure mode the harness exists to replace. A second validation failure means the harness cannot certify this answer and should stop pretending otherwise.

**Auto-repair before asking the model.** G5 supersession and G2 near-miss citation fixes (the model cited a URL that maps to a chunk it did in fact retrieve) are deterministic rewrites. Apply them silently and re-validate before spending a round trip.

**Degrade honestly, never silently.** After a second failure, the turn does not produce a fabricated answer and does not produce a bare error. It produces the retrieved sources plus a statement that Tapio could not confirm the specifics. PRD §7.3 already commits to saying so when no reliable source was found. This extends the same honesty to "I found sources but could not verify my own answer against them," which is a true and useful thing to tell someone.

The degrade path has a second function: it is the instrument. A rising degrade rate in a particular concept area is the primary signal that the register has a gap, which is how the register gets maintained (§9.1).

## 6. Provenance without surveillance

Reproducibility is genuinely useful. If an answer is wrong, knowing which corpus snapshot, which chunks, which register version, and which prompt produced it is the difference between fixing it and guessing. The eval work in #27 needs the same thing.

What is not needed is binding that record to a person. So: a content-addressed provenance record, keyed to the answer rather than the user.

```json
{
  "corpus_snapshot": "sha256:...",
  "register_version": "2026-09-19",
  "chunk_ids": ["...", "..."],
  "plan_hash": "sha256:...",
  "validation_report_hash": "sha256:...",
  "llm_provider": "ollama",
  "model_id": "gemma4@sha256:...",
  "prompt_template_hash": "sha256:..."
}
```

No user identifier, no conversation id, no query text, no signature. Two identical questions produce the same record, which is the point: it describes a *system state*, not an *event*. It can be logged, aggregated, and retained without creating anything a subpoena would want. This is the adaptation of the evidence bundle that fits a product whose users include people for whom a data exposure means exposure to a persecutor.

Every field has to identify something immutable, or the record does not reproduce anything. `model_id` is the field where this is easy to get wrong: `gemma4:latest` is a moving tag, not a version, and a record naming it says only which tag was configured, not which weights answered. Record the resolved digest the provider reports (Ollama exposes one per model; the hosted providers expose dated model identifiers), and resolve it at call time rather than reading it back from configuration. The same rule applies to `register_version`, which is why §7.4 requires dated immutable releases rather than a rolling file. A provenance record that cannot be resolved back to exact inputs is worse than none, because it looks like an audit trail while being a description of intent.

## 7. The register as a longitudinal record

The register has a second life independent of Tapio, and it is worth designing for deliberately because the cost of doing so now is close to zero and the cost of retrofitting it later is not.

### 7.1 What the artifact is

Tapio needs `validUntil` and `supersededBy` for one narrow reason: gate G5, so a guide does not tell someone to visit an office that closed in 2024. But a register that never deletes an entity, records when each one came into and went out of force, and is released as a dated version rather than a rolling file is not just a validation input. It is a **time-indexed, machine-readable record of how the Finnish immigration and integration system changed, year over year, expressed in the terms an immigrant actually encounters.**

As far as we have found, that record does not currently exist in a form anyone can query. The underlying changes are public: they appear in legislation, in agency announcements, and in the sites the crawler already reads. But they are scattered across authorities, published as prose, and each site generally presents only its current state. Nobody maintains the diff.

### 7.2 What it makes answerable

With a time dimension in place, questions like these become queries rather than research projects:

- What did a person applying for a work-based residence permit in March 2024 have to do, and which body did they deal with? Reconstruct the register at a date and read it off.
- How many of the steps in that process changed by 2026, and which ones? A diff between two dated releases.
- What is the churn rate of the administrative surface an immigrant has to learn? Count of concepts added, superseded, or re-scoped per year, by domain. That is a measurable proxy for administrative burden, which is currently argued about qualitatively.
- What happened to the TE Office? Follow the `supersededBy` chain and get lineage rather than a dead link.
- Which authority was responsible for a given service in a given year? The `handledBy` edge, time-sliced.

### 7.3 Who it is for

Tapio itself is one consumer, and the least interesting one. Others:

- **Researchers and anthropologists** studying migration and administrative burden, who currently reconstruct this by hand from archived pages.
- **Planners and municipalities**, who need to know what changed and how the change propagated to the people it affected.
- **NGOs, employers, and advisers** (the partner organizations of PRD §7.7), whose own guidance goes stale for exactly the reasons described in §2.1, and who could check their materials against a dated register.
- **Immigrants themselves**, for the specific and common question "what applied when I arrived," which is often what determines their situation now.
- **Other builders**, since an open SKOS vocabulary aligned to Finto and PTV is reusable infrastructure rather than a Tapio-shaped artifact.

### 7.4 What this adds to the design

Four requirements, all cheap if adopted early and expensive if bolted on later.

1. **Never delete, always supersede.** Removal is a lossy edit. An entity leaves force; it does not stop having existed.
2. **Every concept carries `validFrom`, `validUntil`, and `supersededBy`.** Tapio only reads `validUntil` today. The other two cost nothing to record and are the entire time dimension.
3. **Every assertion carries observation provenance**: which source said this, at what URL, observed on what date. This is what separates a dataset from an opinion, and it is also what lets a reader judge coverage.
4. **Release the register as dated, immutable versions**, not a rolling file. `2026-09-19` is citable; `main` is not. This is also what the provenance record in §6 already references as `register_version`, so the two mechanisms are one mechanism.

**Where an edition lives.** The repository holds the curated source and, per edition, a manifest: the version, the coverage caveat, a coverage summary, and a SHA-256 digest per payload file. The payload itself — the SKOS serializations and the source snapshot — is built from the source by the release command and is not committed, because a register whose every three-line concept change arrives as a fourteen-thousand-line diff is one that stops being reviewed and therefore stops being maintained.

This costs nothing in integrity, provided two properties hold, and both are enforced rather than assumed:

- **The serializations are reproducible.** The same source always produces the same bytes, so a digest identifies an edition rather than one machine's rendering of it. Blank nodes are therefore out: observations carry IRIs, which also makes them citable. Any serializer whose output order is not stable is re-emitted in canonical order.
- **The current edition is rebuilt and checked in CI.** A register edited without bumping its version, a manifest edited by hand, and a change that breaks reproducibility all fail the same check.

Reconstructing an older edition means reading its source snapshot from the commit that added its manifest, which is what git is for. Publication (§7.5) is where the payload gets a durable home outside the repository.

### 7.5 Publication and two caveats

Publish as versioned SKOS in JSON-LD and Turtle, under CC BY 4.0, with the Finto and PTV alignments intact so it composes with existing Finnish vocabulary infrastructure rather than sitting beside it. An open register is also the natural mitigation for the maintenance question in §9.1: a public artifact with outside users attracts corrections that a private one does not.

Two caveats, both important to state in the dataset's own documentation rather than only here.

**This is a byproduct, not a justification.** If the register only made sense as a research dataset, it would not be worth Tapio building. It is worth building because the product needs it. The research value is what makes a small amount of extra rigor in the schema a good trade, not what motivates the work.

**It records what the sources said, not ground truth.** The register's coverage is bounded by the crawled corpus and the seed vocabularies, its observation dates are when Tapio looked rather than when reality changed, and a gap in it is evidence of a gap in Tapio's attention, not evidence that nothing happened. Any published version needs to say this plainly, because a dataset about administrative burden that overstates its own completeness is worse than none.

For a project with no formal organizational backing, this is also the most legible thing it produces to a research funder, a university partner, or a public-sector collaborator. Worth noting, not worth optimizing for.

## 8. Surfacing the worldview

The harness makes Tapio's internal state into data. That opens a product surface that the current architecture cannot support at all, and it is arguably the most useful thing the milestone produces for an ordinary user.

### 8.1 The invisible input

A response today carries two visible explanations: which guide answered, and which sources were read. Both are already implemented and both are good.

There is a third input, it is more consequential than either, and it is invisible. Before anything is retrieved, Tapio has formed a working picture of who is asking: a permit type, a stage in a process, a category of applicant. That picture decided which sources were searched and which next steps were surfaced. If it is wrong, the answer is wrong in a way the reader has no means of detecting, because the prose will be fluent and the citations will be real. They will simply be about someone else's situation.

PRD §2 names the user's core difficulty as working out *which information applies to them*. A panel that shows the working picture is the only place in the interface where that question gets answered directly.

This is also the clearest user-facing return on the milestone. Free prose generation has no state to show, so none of this is buildable before the harness exists.

### 8.2 What it shows, and in what order

The panel sits above the sources, and the ordering carries meaning. Read top to bottom it becomes:

> **who answered** (existing routing event) → **what I am assuming** (new) → **what I read** (existing citations)

which is the actual causal chain of the response. The sidebar stops being three unrelated widgets and becomes a derivation.

Each entry is one `SituationItem` from §3.3, rendered as its plain-language label in the user's language. Never an IRI, never a class name, never a word like "concept," "register," or "graph." The same rule as the progress events in §9.3: the machinery stays invisible.

The `basis` field drives the display, because **inferred state and stated state are different epistemic objects and should not look alike**. Someone who wrote "I'm a student" and a system that guessed it from the word "university" deserve different visual weight, and marking which is which tells the reader where their attention is worth spending.

| Basis | Roughly how it reads | Invites correction? |
| --- | --- | --- |
| `stated` | "You mentioned you are applying as a student" | Rarely, but editable |
| `inferred` | "I am taking this to be a first application. Is that right?" | Yes, primarily |
| `default` | "Assuming you are applying from outside Finland" | Yes |

Language throughout stays tentative and open-ended. "I am taking this to be" rather than "Your status:". The panel is a working hypothesis offered for correction, and it should read like one.

Empty states matter. Most first turns will have little or nothing worth showing, and a mostly-blank panel is noise. It should appear when there is something to say and grow from there, rather than sitting open and empty from the first message.

### 8.3 Correction is the point

A read-only panel is transparency. An editable one is a repair loop with the user inside it, and that is a materially better feature.

When someone changes "student residence permit" to "work-based residence permit," Tapio receives a concept IRI. Not a sentence to parse, not an intent to classify. A precise, already-resolved, language-independent correction that `route`, `retrieve`, and `plan` can consume directly on the next turn.

That is a better input than a clarifying question, and it is better in a way that speaks to the PRD's central observation that newcomers often do not know what to ask. Noticing that something on screen is wrong is a much lower bar than formulating the right question. The panel converts a skill the user may not have into one they certainly do.

One requirement follows: **a correction must visibly change the next answer.** An edit affordance that produces the same response is worse than no affordance, because it teaches the user the panel is decorative and quietly withdraws the trust the feature was meant to build.

### 8.4 Designing against the profile reading

The serious hazard is that this reads as a case file.

PRD §5 and §7.5 are unusually firm: Tapio is not a case service, does not hold anything resembling an individual's file, and treats a data exposure for asylum seekers, undocumented people, and people fleeing abuse as a physical-safety risk. A sidebar that appears to be accumulating facts about someone's immigration status is frightening to exactly those users, and it is frightening whether or not anything is actually stored. Perception does the damage on its own.

Five rules, all of which are cheap if adopted now:

1. **Turn-scoped, not cumulative.** The panel shows what is in play for *this answer*, not a growing dossier. Its size should not monotonically increase over a conversation.
2. **Visibly clearable.** A one-tap "start fresh" that empties it, with the emptying obvious on screen. The ability to make it go away is most of the reassurance.
3. **Framed as assumption, not record.** "What I am assuming for this answer," never "Your situation" or "Your profile." Wording is doing real safety work here, not decoration.
4. **Nothing persists beyond the session** without an explicit, revocable action by the person, and the panel never asks for detail the answer does not need. It displays what was already inferred; it is not an intake form, and it must not become one.
5. **The panel is not a prompt for more.** No empty slots inviting someone to fill in nationality or status. An unknown is simply absent.

There is also a slope worth naming now rather than discovering later. Once the panel exists, the obvious next request is "remember this between sessions so I don't have to say it again." That is a reasonable-sounding feature that walks straight into what the no-PII posture exists to prevent, and it interacts with the durable-conversations work in #16 and #35. Better decided deliberately, in the open, than arrived at by increments.

### 8.5 The way this could backfire

Worth stating plainly because the whole idea rests on an untested assumption.

The hope is that showing the working picture invites correction and lowers false trust. The opposite is possible. A tidy structured panel of stated facts reads as *a system that knows things*. If the state is wrong and confidently rendered next to real citations, it may lend the wrong answer more authority rather than less, and a user who assumes the machine knows their situation is less likely to check than one who assumes nothing.

The mitigations are the tentative wording and the obvious edit affordances above, but they are hypotheses. This belongs in the UX research already on the roadmap (#33, #36), tested with people who are actually unsure of their status rather than with people who built it.

### 8.6 One object, several readers

The panel's contents should be emitted as a typed SSE event carrying concept IRIs plus resolved labels, not as rendered markup. The visual sidebar is one consumer of that event, and deliberately not the only one.

- **Assistive technology** reads structure rather than layout. A typed object with labelled roles and an explicit basis is legible to a screen reader in a way a styled div is not.
- **Other agents** acting for a person can consume it directly: an NGO's or caseworker's own tool wrapping Tapio, or a general assistant a user already relies on. The correction channel works the same way in reverse, since a correction is a concept IRI regardless of whether a finger or a program produced it.
- **The team** gets a debugging and evaluation surface for free. It is the same state the provenance record in §6 describes, without the hashes.

This costs nothing extra. The `situation` slot is already in the answer plan because the pipeline needs it, so emitting it is a serialization decision rather than new work. It does mean the wire format is a small public contract worth versioning from the start, alongside `routing`, `citation`, `guardrail`, `progress`, `token`, and `done`.

### 8.7 Stretch: showing understanding develop, and the paths ahead

Two extensions, both interesting, both held until the simple version has been in front of users.

**How the picture developed.** Rather than only the current state, show its history within the conversation: what was added when, what was inferred versus corrected, what changed as a result. That is a much richer explanation of how Tapio arrived somewhere, and for a process that unfolds over many turns it is closer to how a person would actually explain their reasoning.

**Where it might go next.** For proactive guidance, show the traversal candidates the process graph is holding, not just the current position. A short "you are here, and these are the steps that usually follow" makes the graph legible as a structure rather than as a list of suggestions, and it lets someone see a step coming before they need it.

Two cautions. The first is presentational: a rendered path through a bureaucracy looks more determined than it is, and individual circumstances diverge from the common route constantly. Any such view has to read as *typical* rather than *prescribed*, or it will mislead precisely the people with the least standard situations. The second is the §8.4 hazard again, harder: a conversation-long history of how understanding developed is much closer to the profile reading than a turn-scoped panel, so the ephemerality rules need to be applied more firmly there, not less.

## 9. Cost, risk, and the wait

This section exists because the proposal is more attractive than it is safe, and the risks are specific.

### 9.1 The register will drift, and openness is the mitigation

The register is a curated artifact. Unmaintained, it becomes worse than nothing: it rejects correct answers about entities nobody has registered yet, and the whole benefit of §2.1 inverts.

Tapio is a beta project on an open-source development flow with no formal organizational backing, so the mitigation cannot be a named owner and a review cadence. It has to be structural, which is arguably more robust anyway:

- **The register is a file in the repo, changed by pull request, validated in CI.** A malformed or internally inconsistent register fails the build, the same way a malformed `crisis_resources.yaml` already fails its test.
- **The degrade rate is the work queue.** §5's degrade path logs which concept areas failed validation. That is a ranked, empirical list of register gaps generated by real usage, rather than someone guessing what to add next.
- **Growth only.** Supersede rather than delete (§7.4), so the register never needs a decision about what to remove, which is the decision that usually stalls.
- **Seeded, not authored.** §10 sources most of the initial content from official vocabularies and the existing corpus. The human step is review, not composition.
- **Published.** An open dataset with outside users gets corrections from those users. That is a weak force, but it is a real one, and it is unavailable to a private file.

This does not make the register self-maintaining. It makes neglect visible and recoverable rather than silent and compounding, which is the realistic goal for a project at this stage.

### 9.2 Over-rejection is a real user cost, so measure it before enforcing

A gate that blocks a correct answer because a concept was not registered yet is a worse outcome for that user than an unvalidated answer would have been.

Run every gate in **shadow mode first**: validate, log the result, change nothing about the response. Shadow data gives a false-rejection rate per gate and a ranked list of register gaps, before any user sees a degraded answer. Enforcement is then switched on per gate rather than all at once, against the exit criteria set out in §11.1. G2, the citation gate, will likely clear that bar quickly because its closed set is unambiguous; G1 and G3 should be assumed slowest, since they depend on register coverage.

### 9.3 Latency, and making the wait legible

The guardrails policy records that each classification call took roughly 15 to 45 seconds against local CPU inference, and lists per-turn latency as an unbenchmarked open follow-up. Three of those already run per turn. Adding an unbounded planning call on top could make turns unusable.

Those figures are the local-CPU Ollama case. Since #143 the provider is configuration, so the latency picture is now a deployment property rather than a fixed constraint, and a hosted provider changes it substantially. That widens the range of acceptable designs but does not remove the problem: the local path has to stay usable, because it is the one that keeps a privacy-sensitive deployment possible without sending every question about someone's asylum process to a third party. Treat the local case as the budget to design against, and the hosted case as headroom.

Two responses, and they work on different parts of the problem.

**Reduce the actual wait.** The `validate` node uses no model. The plan schema is deliberately flat and small, because small local models degrade badly on deeply nested schemas. Only `plan` and a possible single `repair` add model calls, and `plan` replaces work the `generate` node was doing anyway rather than adding to it. This still needs benchmarking against the deployment target, not a developer laptop, before the gates ship.

**Make the remaining wait legible.** A silent 30 seconds reads as a broken page. The same 30 seconds with honest progress reads as work being done, and the harness is what makes honest progress possible: the graph's nodes are discrete, named, and sequential, so each transition is a real event to report. Free prose generation has nothing comparable to show, because it is one opaque call.

The SSE stream already carries typed events and `stream_chat_turn` already emits `routing`, `citation`, `guardrail`, `token`, and `done`. The SvelteKit client ignores event types it does not recognize, which the guardrails work already relied on, so a `progress` event is a wire-compatible addition:

| Node | Event | Shown to the user |
| --- | --- | --- |
| `route` | `progress` | "Working out what you are asking about" |
| `route` | `routing` (exists) | "Bringing in Ilmarinen, who handles permits and paperwork" |
| `retrieve` | `progress` | "Looking through official sources" |
| `plan` | `progress` | "Putting together an answer" |
| `validate` | `progress` | "Checking the details against official terms" |
| `repair` | `progress` | "Correcting something that did not check out" |

Three rules for these, because progress messages are easy to get wrong:

1. **Only report state the system is actually in.** Emit on node entry, from the node. A spinner that narrates fictional stages to fill silence is a lie, and a product whose entire value proposition is verifiability should not tell small ones.
2. **Plain language, no system vocabulary.** Users see "checking the details against official terms," not "SHACL validation" or "vocabulary gate." The register, the gates, and the graph are implementation and should stay invisible. Same rule as §8.2.
3. **Localized like everything else.** These strings go through the same language handling as the rest of the response. The guardrail response path already established that Tapio cannot assume users read English.

The `repair` message is the interesting one. Showing that Tapio caught and corrected its own mistake is not an admission of weakness, it is a demonstration of the property the product is selling. Worth testing with users rather than hiding by default.

### 9.4 Streaming

`stream_chat_turn` streams tokens as they arrive. A validate-then-render design cannot stream the plan, because a plan is only checkable once complete.

The workable shape is two-pass: generate and validate the plan, which is small, then stream prose constrained to the validated plan. The user waits through the plan call before the first token appears, which is exactly the wait §9.3's progress events cover. Emitting the validated situation panel and citations as soon as the plan passes, before prose generation starts, turns more of that wait into visible progress: the user can read what Tapio is assuming and where the answer is coming from while it is being written. That ordering is a nice accident of the design rather than something it was built for.

### 9.5 What the harness does not do

It bounds form, not truth. A claim that names a real permit, cites a real retrieved chunk, and stays in scope can still misread what that chunk says. G4 catches some of this by checking that relations make sense, but the harness is not a fact-checker and should not be described as one, internally or to users. It removes a class of failure. It does not remove failure.

## 10. Seeding the register from official sources

The register's IRIs should not be invented where an official Finnish vocabulary already exists. Anchoring to published vocabularies is what makes it an authorized identifier register rather than one more hand-made list, it is the fastest way to fill it, and it is what makes the published dataset in §7 interoperable rather than bespoke.

| Source | What it provides | Access |
| --- | --- | --- |
| **Finto** (finto.fi, api.finto.fi) | National ontology and vocabulary service, National Library of Finland. YSO general ontology and others, as SKOS. Search, URI lookup, and full vocabulary dumps in JSON-LD and Turtle. No API key. Licensed CC0 or CC BY by vocabulary. | REST API |
| **Annif** (ai.finto.fi) | Automated subject indexing against YSO, from the same service. Suggests concepts for a text, single or batched. | REST API |
| **Terminologies** (sanastot.suomi.fi) | Finnish public sector terminologies on the Interoperability platform, run by DVV. Includes public-administration and service terminology. | Web, platform APIs |
| **Reference Data** (koodistot.suomi.fi) | Official code lists from the same platform. | Web, platform APIs |
| **Suomi.fi Service Catalogue (PTV)** | Structured per-municipality and per-county service descriptions, CC0. Already identified in the grounding-sources research as the realistic path to Kokko's data. | Open API |
| The live corpus | Candidate terms mined from crawled Migri, Kela, Vero, DVV, and TE content, as a human review queue. | Local |

Annif deserves a second look beyond seeding. Tagging corpus chunks with YSO concepts at ingest time is what makes concept-based retrieval work, and Annif turns that from a manual annotation project into an API call against a service the National Library already operates.

Two constraints to check before committing. YSO is a general-purpose ontology and its immigration coverage will be uneven, so expect to mint Tapio-local IRIs for domain specifics and map them to YSO with `skos:exactMatch` or `skos:closeMatch` where a match exists, rather than forcing everything into YSO. And the licensing review in the grounding-sources research should be extended to cover any vocabulary imported here, since importing terms is a different reuse pattern from citation-with-link, and publishing the result under CC BY (§7.5) raises the stakes on getting that right.

## 11. Milestone plan

### 11.1 What 2.1.0 should establish

Rather than a phase count, 2.1.0 is best defined by the invariant it makes true, since that is what determines whether later guide work builds on it or around it:

> **No guide ships without a register-backed scope, and no answer ships without register-validated commitments.**

The two halves of that sentence land at different times, and conflating them would contradict the shadow-mode rule in §9.2.

The scope half is immediate and unconditional. A guide's scope is a register concept set from the moment the register exists, and a guide without one does not ship. Nothing is staged about this, because it constrains what the team writes rather than what a user sees.

The validation half is staged, because enforcing an incomplete register on real users is the failure mode §9.2 exists to prevent. 2.1.0 delivers the mechanism in shadow mode: every gate runs on every turn, every result is logged, and no response changes. Enforcement is a later switch, thrown per gate rather than all at once, and only against measured evidence.

**Exit criteria for enforcing a gate.** A gate moves from shadow to enforcing when all of the following hold for it:

1. At least four weeks of shadow data across real traffic, not synthetic queries.
2. A false-rejection rate below an agreed threshold, measured by sampling rejected turns and judging by hand whether the answer was in fact correct. The threshold is per gate and must be set before the data is looked at, not after.
3. The register gaps the shadow data exposed are closed, or explicitly accepted as out of scope for that gate.
4. The repair path resolves a substantial share of failures without a second model call, so enforcement does not simply convert rejections into degraded answers.
5. The degrade path has been reviewed as a user-facing experience by someone who did not build it, since it is what users will actually see when the gate bites.

Expect these to be met at very different times. G2, the citation gate, has an unambiguous closed set and no register dependency, so it should clear the bar quickly and can enforce well before the others. G6 depends on nothing but the register's labels and should follow. G1 and G3 depend on register coverage and should be assumed slowest. G7 is a special case with no shadow period, because its failure mode is a demotion rather than a rejection: showing an unevidenced claim as "you told me" is the harm, and demoting it to "inferred" costs the user nothing.

Everything needed to make the scope half true, and to run the validation half in shadow, belongs in 2.1.0. Enforcement itself does not, and neither does anything that improves answers without being a precondition for the next guide.

| In 2.1.0 | Why it has to be here |
| --- | --- |
| **Citation gate** (no ontology needed) | Independent, cheap, and makes a PRD-committed property true by construction. Land it first. |
| **Term register**, Ilmarinen's domain, roughly 100 to 150 concepts, en/fi/sv, with the §7.4 time fields from day one | The artifact everything else reads. The time fields are cheap now and expensive later. |
| **Answer plan and gates** G1 and G3 through G7, plus the repair and degrade paths, in shadow mode | The validation layer itself. Shadow mode means it can ship without user-visible risk; enforcement follows the §11.1 exit criteria, per gate. G7 is the exception and enforces on arrival, since its failure demotes a label rather than rejecting an answer. |
| **Guide scope as concept sets** | This is the actual reason to do the milestone before more guides. Scope stops being a hand-written English sentence and becomes the thing G3 checks. |
| **Progress events** (§9.3) | The latency mitigation. Shipping the gates without it means shipping a slower product with nothing to show for the wait. |
| **Situation panel, read-only** (§8.1 to §8.6) | Buildable as soon as `plan` populates `situation`, and it is the milestone's only surface an ordinary user can see. Read-only first keeps the scope small and the §8.5 question testable. |
| **Register in CI**, dated releases | The maintenance mechanism from §9.1. Without it the register rots from the first week. |

| After 2.1.0 | Why it can wait |
| --- | --- |
| Situation panel corrections (§8.3) | Needs the read-only version tested first, and the §8.4 persistence boundary decided. Interacts with [#16](https://github.com/Finntegrate/tapio/issues/16) and [#35](https://github.com/Finntegrate/tapio/issues/35). |
| Concept-expanded retrieval, Annif tagging at ingest | Answer-quality improvement, not a precondition. Relates to [#26](https://github.com/Finntegrate/tapio/issues/26). |
| Register coverage for Sampo, Rauni, Otso, then the seven planned guides | Each new guide extends the register as part of its own work, which is the point of the invariant. Relates to [#15](https://github.com/Finntegrate/tapio/issues/15), [#96](https://github.com/Finntegrate/tapio/issues/96), [#121](https://github.com/Finntegrate/tapio/issues/121). |
| Process graph for proactive guidance | Needs the register to exist first. PRD §7.2. |
| Developing-understanding and paths-ahead views (§8.7) | Need the process graph and a tested panel. |
| Provenance record and register-derived eval set | Needs the gates to exist first. [#27](https://github.com/Finntegrate/tapio/issues/27). |
| First public dataset release | Should follow at least a year of dated releases, so the first published version has a time dimension worth reading. §7. |

### 11.2 Ordering within the milestone

The citation gate ships alone and first, because it depends on nothing and proves out the shadow-mode pattern on the cheapest possible check. Register and LinkML schema come next and can proceed in parallel with it. Gates, repair, and scope-as-concepts follow the register. Progress events and the read-only situation panel can be built any time after the graph gains its new nodes, and should not be left until last, since together they are what makes the milestone demoable to someone who does not read code.

### 11.3 Before filing issues

Per `CLAUDE.md`, scan the open backlog before creating anything: several of these overlap existing items (#119 is the register's first consumer, #26 and #68 touch retrieval and sources, #27 is the eval work, #33 and #36 are where the §8.5 question belongs), and they should be filed as follow-ons or consolidations rather than duplicates.

## 12. Stack

| Role | Choice | Note |
| --- | --- | --- |
| Schema source of truth | **LinkML** | One YAML generates Pydantic, JSON Schema, SHACL, and OWL. Python-native, fits the existing uv and Pydantic setup. |
| Constrained generation | **`BaseChatModel.with_structured_output`** | Already in `guardrails/llm_classifier.py`, and provider-independent since #143. No new dependency. |
| Graph handling | **rdflib** | In-memory is fine at this size. Do not reach for a triplestore before the register outgrows a dict. |
| Shape validation | **pySHACL** | Compile shapes once at startup, not per request. |
| Entity resolution | **The model, in `plan`** | A concept is named by the model and checked by G1. No matcher, no lexicon of inflected forms. |
| Graph store | **Not yet.** pyoxigraph if the register outgrows memory | Deliberately deferred. |
| DL reasoner | **None** | See §4. |
| Policy engine | **None** | See §4. |

The one deliberate dependency addition is LinkML plus pySHACL plus rdflib. Everything else is already present or explicitly declined.

## 13. Open questions

| Question | Blocking? |
| --- | --- |
| Does showing the working picture (§8) invite correction and lower false trust, or does a tidy structured panel make Tapio read as more authoritative? The whole feature rests on this and it is untested. Belongs in [#33](https://github.com/Finntegrate/tapio/issues/33) / [#36](https://github.com/Finntegrate/tapio/issues/36), with people who are genuinely unsure of their status. | Yes, before corrections are built on top |
| What is the persistence boundary for the situation panel? Turn, session, or explicitly pinned by the user? §8.4 argues for turn-scoped with visible clearing, but this collides with durable conversations ([#16](https://github.com/Finntegrate/tapio/issues/16), [#35](https://github.com/Finntegrate/tapio/issues/35)) and should be settled jointly rather than twice. | Yes, for the panel |
| Does the plan-then-stream latency (§9.4) produce an acceptable first-token wait on the deployment target, with progress events in place? Needs a benchmark, not an opinion. | Yes, before the gates leave shadow mode |
| Where do Tapio-local concept IRIs live, and what is the policy for minting one rather than reusing a YSO or PTV identifier? This also determines whether the published dataset has stable, resolvable identifiers. | Yes, for the register |
| Does importing terms from the sources in §10 raise licensing questions the grounding-sources research did not cover, given it assessed citation-with-link rather than reuse and republication under CC BY? | Yes, before first publication, not before first use |
| Is a concept-level situational context (permit type, stage, applicant category) sufficient for useful proactive guidance, and does it satisfy the no-PII posture? This proposal argues yes but has not tested it. | Yes, for the process graph |
| Should the register cover all 12 languages InfoFinland publishes in, or the three the corpus is grounded in? | No, three is a fine start |
| Does an official or academic record of Finnish immigration-system changes over time already exist in machine-readable form? §7.1 assumes not, based on a survey that was not exhaustive. Worth an hour of checking before building on the assumption. | No, but it changes how §7 is framed |

## 14. Sources

- Finto API documentation, National Library of Finland: <https://api.finto.fi/>
- YSO General Finnish Ontology: <https://finto.fi/yso/en/>
- Terminologies service, Interoperability platform, DVV: <https://sanastot.suomi.fi/en/site-information>
- Suomi.fi Service Catalogue (PTV), per the grounding-sources research: <https://kehittajille.suomi.fi/>
