# ADR 0004: Adopt CocoIndex and Postgres/pgvector for the ingestion service

## Status

Proposed

## Date

2026-07-25

## Context

Tapio's current vectorization stage (`tapio/vectorstore/`) chunks parsed Markdown with LangChain text splitters and embeds it into ChromaDB, a local, file-based (or client-server) vector store. This code is invoked via the `vectorize` CLI command as part of a single-project pipeline (crawl → parse → vectorize → serve).

[ADR 0002](0002-monorepo-service-split.md) separates this pipeline into independently-owned projects: `crawler/` produces Markdown, `ingest/` turns that Markdown (and PDFs) into vectors, and `tapio/` serves the app by reading from the resulting vector store. This ADR covers the technology choice for the new `ingest/` project.

[CocoIndex](https://github.com/cocoindex-io/cocoindex) is an open-source (Apache 2.0), Python-with-a-Rust-core ETL framework purpose-built for this kind of workload:

- **Incremental processing** — it tracks state at the file/content level and only reprocesses what actually changed, rather than re-embedding an entire corpus on every run. This matters here: we crawl five government sites, most of which change incrementally, not wholesale, between runs.
- **Built-in operators** — text chunking (e.g. `RecursiveSplitter`) and embedding (`SentenceTransformer`, `LiteLLM`), covering what `tapio/vectorstore/vectorizer.py` currently does by hand.
- **PDF handling** — CocoIndex has demonstrated examples for converting PDFs to Markdown and for structured extraction from PDFs (including via Document AI or vision-model-based parsing), which is relevant since the user asked for PDF ingestion, not just Markdown.
- **Native Postgres/pgvector output connector** — pgvector is one of CocoIndex's first-class supported vector-store targets, alongside Qdrant, LanceDB, Neo4j, and others.
- **Uses Postgres as its own metadata/state store** — CocoIndex tracks incremental-processing state in Postgres regardless of which vector store it writes to. This means a single Postgres instance (with the `pgvector` extension enabled) can serve two roles at once: CocoIndex's internal bookkeeping and the actual vector store Tapio queries at retrieval time — one database to provision and operate instead of two separate stores.

This is presented as a firm decision rather than a formally evaluated comparison against Qdrant/LanceDB/keeping ChromaDB, on the reasoning above (single Postgres instance minimizes infrastructure). It has not yet been validated with a hands-on spike the way the crawler decision was (ADR 0003) — see Risks.

## Decision

We will adopt CocoIndex as the ingestion framework, in the new root-level `ingest/` project ([ADR 0002](0002-monorepo-service-split.md)), writing to Postgres with the `pgvector` extension as the vector store.

`ingest/` will:

- Read Markdown output (with YAML frontmatter, including the canonical `source_url`) produced by `crawler/` ([ADR 0003](0003-crawl4ai-crawler.md)), plus PDFs where applicable.
- Chunk and embed content using CocoIndex's built-in operators, retaining `all-MiniLM-L6-v2` as the embedding model (current stack choice, unchanged by this ADR — revisiting the embedding model is a separate decision).
- Write vectors and metadata (including `source_url`, for RAG citation/grounding) to Postgres/pgvector.
- Use the same Postgres instance for its own incremental-state tracking.

`tapio/` will connect **directly** to this Postgres/pgvector instance for retrieval (e.g. via LangChain's `langchain-postgres` `PGVector` integration, replacing `langchain-chroma`), rather than going through a separate retrieval API. This keeps the app's retrieval path simple — one database connection, no extra service to run or version — at the cost of coupling `tapio/`'s expectations to `ingest/`'s output schema. That coupling is judged acceptable within a single monorepo where both projects' schemas can be changed together.

### What changes

- `tapio/vectorstore/chroma_store.py` and the `vectorize` CLI command are removed from `tapio/`.
- `tapio/vectorstore/vectorizer.py`'s manual chunking/embedding orchestration is superseded by CocoIndex's built-in operators, configured in `ingest/`.
- `tapio/` keeps only retrieval-side code: a `PGVector`-based retriever (or equivalent direct query layer) used by the RAG chain/agents.
- `langchain-chroma` is dropped from `tapio/`'s dependencies; a Postgres/pgvector client (e.g. `langchain-postgres`, `psycopg`) is added.
- Local development requires a running Postgres instance with `pgvector` enabled, provisioned via a shared `docker-compose.yml` at the repository root (per ADR 0002).

## Consequences

### Positive

- **Incremental ingestion** — avoids re-embedding unchanged pages on every run, which matters as the corpus grows across five-plus government sites re-crawled periodically.
- **Mostly single database to operate** — one Postgres instance serves as the vector store itself, instead of running Chroma plus whatever else. (Corrected by the spike below: CocoIndex's own incremental-processing state is *not* stored in Postgres in the current version, so this isn't quite "one database total" — see "Spike results.")
- **Mature, well-supported target** — Postgres/pgvector has strong LangChain ecosystem support and is a well-understood operational choice at this project's scale.
- **PDF support out of the box** — addresses the stated need to ingest PDFs, not just crawled Markdown, without hand-rolling extraction.
- **Decoupled ingestion cadence** — `ingest/` can run on its own schedule (e.g. after each `crawler/` run), independent of both crawling and the app's uptime.

### Negative

- **New operational dependency** — the project currently has no database server to run (ChromaDB is embedded/file-based); Postgres now needs to be provisioned and operated in dev, CI, and production.
- **A second, non-Postgres state store** — CocoIndex tracks its own incremental-processing state in a local embedded LMDB directory (`COCOINDEX_DB`), not in Postgres (confirmed by the 2026-07-25 spike, correcting this ADR's original assumption). That directory needs to be a persistent volume in any real `ingest/` deployment, or every run becomes a full re-index.
- **CocoIndex is a young project** — maturity, release cadence, and community size should be checked directly before this ADR moves from Proposed to Accepted; being new increases the risk of breaking changes or gaps in documentation.
- **Less granular control over chunking/embedding** — logic that currently lives in our own `vectorizer.py` moves into CocoIndex's configuration surface. This is a net simplification if CocoIndex's configuration is expressive enough for our needs, but that has not yet been validated hands-on.
- **Direct DB coupling** — `tapio/` depends on `ingest/`'s Postgres schema directly; schema changes need coordinated updates across both projects (the same cross-project contract risk noted in ADR 0002).

### Risks

- ~~**Unvalidated in practice**~~ — resolved by the fail-fast spike below (2026-07-25): the mechanical pipeline (chunk → embed → write → query) works end-to-end against real Crawl4AI output. Two corrections surfaced by running it are folded into the Positive/Negative sections and detailed in "Spike results."
- **PDF ingestion path unverified** — CocoIndex's PDF examples exist, but which approach (direct Markdown conversion vs. Document AI vs. vision-model extraction) fits our needs and cost constraints hasn't been chosen or tested. Not covered by the 2026-07-25 spike, which used Markdown only.
- **Schema/contract drift** — as with the `crawler/` → `ingest/` handoff, the `ingest/` → `tapio/` handoff (the Postgres schema itself) needs to be explicit and tested, not just assumed stable.

## Spike results (2026-07-25)

Ran a fail-fast, hands-on validation of this ADR using the official CocoIndex `text_embedding` example, adapted to read the five Markdown files produced by the Crawl4AI experiment ([ADR 0003](0003-crawl4ai-crawler.md)), against a disposable `pgvector/pgvector:pg17` Docker container. CocoIndex v1.0.18, Python 3.13.

**End-to-end pipeline confirmed working**: Markdown in → CocoIndex `RecursiveSplitter` chunking → `SentenceTransformerEmbedder` (`all-MiniLM-L6-v2`) → `postgres.TableTarget` write → cosine-similarity query, all mechanically validated. 147 chunks were produced from the five front pages and successfully queried back.

Two corrections to this ADR's reasoning, found only by running the spike:

1. **CocoIndex does not use Postgres as its own metadata store in the installed version (v1.0.18)** — it uses a local, embedded LMDB store (`COCOINDEX_DB` environment variable, pointing at a filesystem directory) for its own incremental-processing state. Postgres/pgvector is used purely as a *target* connector for the vectors themselves. This invalidates the "single Postgres instance serves both roles" reasoning in this ADR's Context and Positive consequences — that claim came from web research describing CocoIndex's general architecture, not from exercising the actual current API. **Infrastructure footprint is therefore: one Postgres/pgvector instance (data) + a small local LMDB directory per `ingest/` deployment (state)** — still lightweight, but not literally "one database," and the LMDB state directory needs to be a persistent volume in any real deployment (losing it would force a full re-index, defeating the incremental-processing benefit).
2. **The default vector index type is a correctness footgun on small-to-medium corpora.** `TableTarget.declare_vector_index()` defaults to `method="ivfflat"` with unspecified `lists`. At our test scale (147 rows), IVFFlat's default `probes=1` caused queries to silently return far fewer rows than requested (1 row instead of the requested top-5) — no error, just a quietly wrong result set. Switching to `method="hnsw"` (also directly supported by CocoIndex's API) returned the full requested result count by default with no query-time tuning needed. **Recommendation: use `method="hnsw"` in the real `ingest/` implementation**, not the `ivfflat` default shown in CocoIndex's own reference example.

Other observations:

- **Retrieval quality on this corpus was weak** (cosine similarity scores in the 0.2–0.4 range, top matches often navigation-menu link lists rather than substantive content). This reflects the *test corpus*, not CocoIndex: the Crawl4AI spike only crawled front pages, which are nav-heavy and low in instructional content. It's a reminder that the real `crawler/` implementation needs multi-page/deep crawling (sitemap-driven or link-following) to produce a corpus worth retrieving from — a front-page-only crawl is not sufficient input for either this ADR or ADR 0003 in production.
- **Query-side code in CocoIndex's own examples uses raw `asyncpg` and hand-written SQL**, not a LangChain retriever. This ADR's Decision states `tapio/` will connect via `langchain-postgres`'s `PGVector` integration — that remains viable since LangChain's `PGVector` doesn't require its schema to be created by LangChain itself, but the choice between hand-rolled `asyncpg` queries (CocoIndex's own idiom) and `langchain-postgres` is an open implementation detail that should be settled when `ingest/` and `tapio/`'s retrieval code are actually built, not assumed.
- **Setup cost was low**: installing CocoIndex, `sentence-transformers`, `asyncpg`, and the `pgvector` Python client, plus a disposable `pgvector/pgvector:pg17` container, took a few minutes; indexing the five-file/147-chunk test corpus took ~44 seconds end-to-end on CPU, including one-time embedding-model download/warm-up. Not a concern at current scale; worth revisiting if the corpus grows to hundreds of pages.

This ADR remains Proposed. The mechanical pipeline is now validated; the two corrections above (LMDB state store, HNSW over IVFFlat) should be folded into the real `ingest/` implementation. The PDF ingestion path (flagged as unverified in the original Risks section) has still not been tested.

## Alternatives considered

### 1. Keep ChromaDB

Rejected per ADR 0002's decoupling goal: Chroma is typically used embedded/file-based, which doesn't fit cleanly into a fully separate ingestion service and a fully separate app service talking to it independently. Chroma's client-server mode exists but is less common and less battle-tested than Postgres/pgvector for this pattern.

### 2. Roll our own ingestion script against pgvector directly

Keep hand-written chunking/embedding code (as today) but point it at Postgres/pgvector instead of Chroma. Rejected because this re-implements incremental/delta processing and change detection that CocoIndex provides out of the box — undermining the same "minimal maintenance, single responsibility" reasoning behind the crawler decision in ADR 0003.

### 3. Qdrant or LanceDB as the vector store

Both are supported CocoIndex targets and were considered. Rejected under the "firm decision" framing adopted for this ADR: a single Postgres instance serving both CocoIndex's metadata store and the vector store minimizes infrastructure surface compared to running Postgres *and* a separate vector-specific database. This trade-off could be revisited if pgvector's performance or feature set proves insufficient at scale.

## References

- [ADR 0002: Split the repository into independent crawler, ingest, and app projects](0002-monorepo-service-split.md)
- [ADR 0003: Adopt Crawl4AI for the crawler service](0003-crawl4ai-crawler.md)
- [CocoIndex GitHub repository](https://github.com/cocoindex-io/cocoindex)
- [CocoIndex + pgvector setup guide](https://dev.to/cdnsteve/setting-up-cocoindex-with-docker-and-pgvector-a-practical-guide-3mag)
- [langchain-postgres PGVector integration](https://python.langchain.com/docs/integrations/vectorstores/pgvector/)
