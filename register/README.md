# Tapio term register

The versioned term register: the closed-world authority over which entities a
guide answer may assert, and a time-indexed record of how the Finnish
immigration and integration system changes.

It is the artifact the rest of the ontological harness reads — answer-plan
gates, guide scope as concept sets, the process graph, and register CI all
resolve against it. See
[ADR 0007](../docs/ADRs/0007-ontological-harness.md) and the
[ontological harness specification](../docs/specs/ontological-harness.md).

This edition covers **Ilmarinen's domain**: residence permits, visas, and the
application process, together with the authorities, documents, statuses, and
legal acts those answers have to name. Sampo, Rauni, and Otso extend the same
register rather than starting new ones.

## What is in here

| Path | What it is |
| --- | --- |
| `tapio_register/schema/term_register.yaml` | The LinkML schema. The single source of truth. |
| `tapio_register/data/` | The curated register: `edition.yaml` for the edition's own metadata, and one file per kind of concept. A concept's id prefix says which file it belongs in, and the loader refuses a concept filed under the wrong kind. |
| `tapio_register/generated/` | Pydantic classes and JSON Schema, both derived from the schema. Never hand-edited. |
| `candidates/` | Seeding output awaiting review. Not part of the register until a person moves a term into `register.yaml`. |
| `releases/<date>/manifest.json` | One dated, immutable edition: its coverage summary and a SHA-256 digest per payload file. |
| `evals/concept-resolution.yaml` | 30 real-shaped queries in Finnish, Swedish and English — inflected, misspelled, code-switched, obsolete, ambiguous — with the concepts each should resolve to. What a classifier has to get right before the register is worth feeding it. |

## Working with it

```bash
mise run register:validate      # schema, SHACL, and integrity checks
mise run register:generate      # regenerate the derived artifacts after a schema change
mise run register:release       # build the edition named by the source's register_version
mise run test:register          # unit tests
```

Two projections turn the register into what a model consumes:

```bash
uv run --directory register tapio-register options --guide ilmarinen   # what a classifier picks from
uv run --directory register tapio-register context permit:extended-permit org:te-office
```

The first is one line per concept, scoped to a guide, small enough for a
prompt. The second is the facts a guide should generate against for the
concepts one turn is about — including, for something no longer in force, when
it lapsed and what replaced it.

## How an edition is stored

Only `manifest.json` is committed. The payload it describes — `register.ttl`,
`register.jsonld`, and the `register.yaml` snapshot — is built by
`register:release` and is git-ignored, because committing it would bury a
three-line concept change in a fourteen-thousand-line diff, and a register that
is hard to review is a register that stops being maintained.

Nothing is lost by this. The serializations are byte-reproducible from the
source (observations carry IRIs rather than blank nodes, and the JSON-LD is
re-emitted in canonical order), so `tapio-register verify-releases` rebuilds the
edition the source names and checks it against the recorded digests. That one
check catches a register edited without a version bump, a hand-edited manifest,
and any change that breaks reproducibility. To reconstruct an older edition,
check out the commit that wrote its manifest and run `register:release`.

Two things do not need that, because each manifest records its own concept ids:
the cross-edition continuity check, which proves nothing was dropped, and
`tapio-register diff`, which falls back to comparing those ids when no payload
is built. The fallback answers what came and went but not what changed inside a
concept, and says which of the two comparisons it made.

`--overwrite` is the one way an edition can change identity while keeping its
version. It exists for correcting an edition that has not been merged, it names
what it changed when it is used, and a manifest is never marked as generated —
so an edition changing identity always shows up as a reviewable diff. Once an
edition is on `main`, treat it as published: bump `register_version` instead.
Enforcing that boundary needs a home for published editions outside this
repository, which is [#168](https://github.com/Finntegrate/tapio/issues/168).

Seeding candidates from Finto reaches the network and is run by hand, not in
CI:

```bash
uv run --directory register tapio-register seed-finto oleskelulupa viisumi
```

## What a consumer needs

Reading the register needs the data, the generated Pydantic module, and
`loading.py` — so pydantic and pyyaml, and nothing else. Those are the package's
only mandatory dependencies. LinkML, rdflib, jsonschema, typer and httpx are
authoring-time only — they generate artifacts, publish SKOS, validate, and seed
candidates — and live in the `authoring` extra, which is what the
`tapio-register` command and the test suite need:

```bash
uv sync --all-extras
```

So a service that only reads the register does not install the toolchain that
builds it, and a test fails if a convenience import ever puts one of those
libraries back on the read path.

Nothing in the read path reaches outside the package — no network, no
subprocess, no repository history — so it behaves the same in a container with
no `.git` as it does in a checkout.

## The rules this artifact lives by

These come from ADR 0007 and are enforced by `tapio-register validate`, not
left to reviewer discipline.

1. **Never delete, always supersede.** An entity that leaves force gains a
   `valid_until` and a `superseded_by` pointer. Removal would be a lossy edit:
   the entity stopped being in force, it did not stop having existed.
2. **Every concept carries `valid_from`, and `valid_until` plus `superseded_by`
   once it lapses.** Gate G5 reads `valid_until`; the other two are what make a
   historical question answerable at all.
3. **Every concept carries observation provenance** — which source said this, at
   what URL, observed on what date.
4. **Editions are dated and immutable.** `2026-09-19` is citable; `main` is not.
   A provenance record's `register_version` names an edition in `releases/`.

## What this records, and what it does not

The register records **what its sources said, on the dates they were observed**.
It is not ground truth. Its coverage is bounded by the crawled corpus and the
seed vocabularies, its observation dates are when Tapio looked rather than when
reality changed, and a gap in it is evidence of a gap in Tapio's attention, not
evidence that nothing happened.

`valid_from` is the earliest date from which the register is prepared to treat
an entity as in force, not a claim about when it was created. Where a source
names a commencement date, that date is used — the wellbeing services counties
from 1 January 2023, the municipal employment areas from 1 January 2025, the
Economic Development Centres from 1 January 2026. Otherwise it is the register's
floor date of 1 May 2004, the commencement of the Aliens Act (301/2004), which
records that no start date has been established. A date not stated by one of the
cited sources is the register's own best evidence and is open to correction —
which is one of the things publishing the register openly is for.

Nothing in it is legal advice, and an entry being in force is a statement about
a published source, not about any individual's case.

## Licence

The register data (`tapio_register/data/` and everything under `releases/`) is
released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), so it
composes with the Finnish vocabulary infrastructure it aligns to. The tooling in
this directory is MIT, like the rest of the repository.
