# Guide network — grounding source research

**Status:** Research complete, pending review

**Owner:** Finntegrate

**Related:** [Planned guide network expansion spec](../specs/planned-guide-network-expansion.md), [PRD §6](../PRD.md#6-the-guide-network), [issue #96](https://github.com/Finntegrate/tapio/issues/96), [issue #121](https://github.com/Finntegrate/tapio/issues/121)

## Purpose

The [planned guide network expansion spec](../specs/planned-guide-network-expansion.md) scopes all seven planned guides but flags several open questions about whether groundable sources actually exist for each domain — Louhi's source-policy question, Ahti's fragmented-source concern, Kokko's missing municipal aggregator. This document resolves those questions with concrete candidate sources, checked for authority, license, language coverage, and crawlability, plus a spot-check of the five sources already live in [`crawler/tapio_crawler/config/site_configs.yaml`](../../crawler/tapio_crawler/config/site_configs.yaml).

Crawlability notes below reflect `robots.txt` as fetched 2026-09-16. `robots.txt` can change; re-check before wiring a source into `site_configs.yaml`, and check actual fetch behavior with the crawler's own user agent — bot-detection (e.g. Cloudflare) can differ from what `robots.txt` declares.

## Spot-check: the 5 live sources

| Source | Domain | Guides it grounds | robots.txt | Notes |
| --- | --- | --- | --- | --- |
| Migri | migri.fi | Ilmarinen | `Crawl-delay: 5`, sitemap present, AhrefsBot/MJ12bot/SemrushBot blocked | Matches `site_configs.yaml`'s `min_delay: 5.0` |
| TE / Job Market Finland | tyomarkkinatori.fi | Sampo | No sitemap declared, no disallow | Matches config's `discovery: none` + bounded gap-crawl |
| Kela | kela.fi | Rauni, Mielikki (candidate) | Sitemap present, no crawl-delay declared | Already grounds health-insurance content Mielikki would also need |
| Vero | vero.fi | Rauni, Pellervo (candidate) | Sitemap present, no crawl-delay declared | Already grounds the tax content Pellervo's "entrepreneur tax obligations at a general level" line needs |
| DVV | dvv.fi | Otso, Ahti (candidate) | `Crawl-delay: 5`, AhrefsBot/MJ12bot/SemrushBot blocked | Already grounds the address-registration content Ahti's "postal address, DVV population information" line needs |

Two of the five live sources — Vero and DVV — already partially ground planned guides (Pellervo and Ahti respectively). That overlap should be accounted for in build effort estimates: those guides don't start from zero corpus coverage.

## Per-guide candidate sources

### Pellervo (entrepreneurship)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| PRH (prh.fi) | Finnish Patent and Registration Office — business registration, Business ID | FI, SV, EN | No `robots.txt` found (404) — no declared crawl restriction | Centralized |
| Vero (vero.fi) | Tax Administration | FI, SV, EN | Already live | Centralized |
| Business Finland (businessfinland.fi) | State export/investment promotion, startup grants | FI, EN | Sitemap present, no crawl-delay | Centralized |
| ELY Centre (now elinvoimakeskus.fi) | Regional startup support | FI, SV, EN | Sitemap present, no crawl-delay | Note: ELY Centres were renamed/reorganized as Elinvoimakeskus during 2025–2026; the spec's "ELY Centre" reference should be updated to the current name before build |

**Verdict: centralized.** Matches the spec's build-order rationale. One correction: ELY Centre's successor domain should replace the old name in the spec.

### Agricola (language and education)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| InfoFinland (infofinland.fi) | KEHA Centre (nationwide multilingual integration content, transferred from City of Helsinki 1 Jan 2026) | 12 languages | Sitemap present, no crawl-delay declared | Centralized |
| Opintopolku / Studyinfo (opintopolku.fi) | Finnish National Agency for Education — study paths, applications | FI, SV, EN | `Crawl-delay: 30`, sitemap present | Centralized, but the 30s delay is the longest of any candidate source — budget crawl time accordingly |
| OPH (oph.fi) | Finnish National Agency for Education — qualification recognition | FI, SV, EN | No crawl-delay declared | Centralized |

**Verdict: centralized**, confirming the spec's #1 build-order ranking. InfoFinland alone covers most of Agricola's in-scope topics.

### Louhi (culture and etiquette)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| InfoFinland (infofinland.fi) | KEHA Centre | 12 languages | Sitemap present | Centralized |
| Yhteiskuntaorientaatio (yhteiskuntaorientaatio.fi) | KEHA Centre — statutory multilingual civic orientation curriculum, content by the Finnish Refugee Council and Finnish National Agency for Education | Multiple, EN confirmed | Sitemap present, no disallow for `*`; fetched successfully via both `curl` and `WebFetch` during this research (Cloudflare-fronted, but not observed to block automated fetches) | Centralized |

**This resolves the spec's open source-policy question.** The spec asked "which sources count as groundable for this guide" and worried fewer government sources exist for etiquette than for the other domains. Civic orientation (yhteiskuntaorientaatio.fi) became a statutory part of the municipal integration programme in 2025 specifically to cover this content, with national-agency-produced material — it is as groundable as any other guide's sources, not merely "curated cultural-integration content" as the spec anticipated. The open question is resolved: yes, official sources exist.

### Mielikki (healthcare navigation)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| Kela (kela.fi) | Social Insurance Institution — health insurance, EU health insurance card | FI, SV, EN | Already live | Centralized |
| THL (thl.fi) | Finnish Institute for Health and Welfare — system-navigation guidance | FI, SV, EN | `Crawl-delay: 5`, AhrefsBot/MJ12bot/SemrushBot blocked | Centralized |
| Omaolo (omaolo.fi) | National symptom-checker / service-navigation tool, run by a wellbeing-services-county consortium | FI, SV, EN | No `robots.txt` found | Centralized (national front end) |
| Individual wellbeing services counties (21 counties + Helsinki, e.g. `hyvinvointialue.fi` sites) | Regional — appointment booking, local fees, dental/maternity service listings | Varies by county | Not checked individually — 22 separate sites | Fragmented |

**This corrects the spec's assumption.** The spec calls Mielikki's sources centralized, matching Kela/THL/public-healthcare-portals. National *rules* (insurance eligibility, co-pay structure) are centralized through Kela and THL. But the practical "how do I register with a health center" / "find a dentist accepting new patients" answers the spec's own example queries ask for live at the level of 21 wellbeing services counties plus Helsinki, each with its own site, since the 2023 health/social/rescue-services reform moved service organization to that layer. A build should ground national rules from Kela/THL and treat per-county service-finding as either out of scope for v1 or a follow-on ingest task, not assume one centralized crawl covers both.

### Lempi (mental health and community)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| THL (thl.fi) | System-level mental-health service navigation | FI, SV, EN | Same as above | Centralized |
| MIELI ry (mieli.fi) | Largest NGO mental-health provider — peer support, crisis chat/line pointers | FI, SV, EN, AR, RU (per-language sitemaps) | Sitemap present, no crawl-delay declared | Centralized for NGO-sector content |

Not re-assessed for build readiness beyond source availability — the spec's blocking dependency on the guardrail/escalation work (#29) and an approved crisis-resource list (#102) stands regardless of source quality, since this domain is crisis-adjacent per PRD §7.4.

### Ahti (transportation, utilities, banking)

| Source | Authority | Languages | robots.txt | Verdict |
| --- | --- | --- | --- | --- |
| DVV (dvv.fi) | Address registration, population data | FI, SV, EN | Already live | Centralized |
| Traficom (traficom.fi) | Driving license conversion | FI, SV, EN | Sitemap present, no crawl-delay declared | Centralized |
| Regional transit authorities (e.g. HSL for the Helsinki region) | Public transport | Varies by region | HSL: sitemap present, no crawl-delay | Fragmented — no national transit-information aggregator; each region publishes independently |
| Banks | Account opening | Varies by bank | Not checked — no single regulator (FIN-FSA) page aggregates consumer account-opening guidance across banks | Fragmented |

**Confirms the spec's fragmentation concern.** DVV and Traficom are centralized and ready. Transit and banking are genuinely fragmented with no aggregator; the spec's instinct to check corpus coverage before build is correct, and a v1 scope that leans on DVV/Traficom while treating transit and banking as a smaller, curated source set (rather than a full crawl) is more realistic than committing to full coverage up front.

### Kokko (municipal and regional)

| Source | Authority | Languages | Access | Verdict |
| --- | --- | --- | --- | --- |
| Suomi.fi Service Catalogue (PTV) Open API | Digital and Population Data Services Agency — structured, per-municipality and per-wellbeing-county service descriptions | FI, SV, EN (varies by entry) | Open API, CC0 license, `kehittajille.suomi.fi` | Centralized data source, but not a crawl target |
| Individual municipality websites | Municipality-specific pages/contacts | Varies | Hundreds of separate sites | Fragmented |

**This confirms and refines the spec's infrastructure-dependency concern.** No crawlable national aggregator of municipal-service *pages* exists — municipal websites remain fragmented, matching the spec's assessment. However, the Suomi.fi Service Catalogue (PTV) Open API is a realistic path to the same underlying data: it's a structured, CC0, nationally maintained API rather than a set of pages to crawl. This changes the shape of the work from a `crawler` source addition (as the spec's "outside this PRD's scope" note assumed) to an **ingest adapter** that consumes a structured API — a different backlog item than a new `site_configs.yaml` entry, worth filing separately if Kokko is picked up.

## The Otso gap

Otso is live (PRD §6) but has no dedicated entry in `site_configs.yaml` — housing/tenant-rights content isn't grounded by any of the five live sources. Two centralized sources close this:

- **InfoFinland** (infofinland.fi) — has a dedicated Housing section including tenancy-agreement guidance, in 12 languages, CC BY 4.0 (attribution to InfoFinland.fi required).
- **KKV** (kkv.fi) — Finnish Competition and Consumer Authority; publishes tenant-rights, security-deposit, and rent-dispute guidance in FI/SV/EN, sitemap-crawlable, no crawl-delay declared.

Together with Kela (housing benefit, already live), these two cover Otso's full current scope (housing search, rental agreements, tenant rights, housing benefits) and are not currently in `site_configs.yaml`. Filing a follow-on `crawler`/`rag` issue to add InfoFinland and KKV as sources for the *existing* Otso guide is independent of any of the seven planned guides and could ship sooner.

**Boundary note:** Otso's current definition (`backend/app/agents/definitions.py`) describes its summary as helping with "housing, rental agreements, tenant rights, and settling into daily life." Ahti's planned scope is "everyday registration logistics" and general daily-life navigation. "Settling into daily life" in Otso's summary overlaps Ahti's planned domain. If Ahti is built, Otso's summary/out-of-scope line should be tightened to name Ahti as the boundary, the way the spec already does for Mielikki/Rauni.

## Licensing summary

| Source | License / reuse terms |
| --- | --- |
| InfoFinland | CC BY 4.0 — attribution to InfoFinland.fi with a link and license mention required on any citation |
| Suomi.fi Service Catalogue (PTV) | CC0 — no attribution required |
| Yhteiskuntaorientaatio.fi | No explicit reuse license found on the page checked (`/en/about-the-site`); only a standard "© KEHA Centre" notice — treat as all-rights-reserved for redistribution purposes until a license is confirmed with the publisher, even though crawling for RAG grounding (citation-with-link, not redistribution) is the same pattern already used for Migri/Kela/Vero/DVV |
| Migri, Kela, Vero, DVV, THL, PRH, Traficom, KKV, Business Finland, Opintopolku | No open-content license found; treated the same as the five already-live sources — grounded via citation-with-link, not verbatim redistribution |

## Comparison against the spec's build order

The spec ranks guides 1–7 by demand, source availability, and blocking dependencies. This research affects that ranking in two places:

| Guide | Spec's order | This research |
| --- | --- | --- |
| Agricola | 1 | Confirmed — centralized, no complications |
| Mielikki | 2 | **Lower than spec assumed.** National rules are centralized (Kela/THL), but the service-finding half of its own example queries depends on 22 separate wellbeing-county sites, not one centralized crawl. Effort is closer to Ahti's than to Agricola's |
| Pellervo | 3 | Confirmed, with a name correction (ELY Centre → Elinvoimakeskus) |
| Ahti | 4 | Confirmed fragmented; DVV/Traficom are ready, transit/banking are not |
| Louhi | 5 | **Higher than spec assumed.** The spec's blocking source-policy question is resolved — yhteiskuntaorientaatio.fi plus InfoFinland are as groundable as any other guide's sources. Nothing in source availability blocks Louhi; it could move up |
| Lempi | 6 | Unchanged — blocked on #29/#102 regardless of source quality |
| Kokko | 7 | Unchanged in rank, but the nature of the work changes: an ingest adapter against the PTV Open API, not a `crawler` source addition |

**Open item for reviewers:** should the spec's build order change to reflect that Louhi's blocking question is resolved and Mielikki's source picture is more complex than assumed, or should build order stay demand-led (healthcare need outweighs a lower-effort win on cultural orientation) regardless of relative effort? This research surfaces the trade-off; it doesn't resolve it.

## Other open items for reviewers

- Kokko's example query in the spec ("Where's my nearest TE Office in Turku?") is stale — TE Offices were dissolved and their services transferred to 45 municipal employment areas on 1 January 2025. The spec's example queries should be updated wherever they reference TE Offices as physical local entities.
- `robots.txt` was checked for every candidate source in this document as of 2026-09-16 but not re-verified against actual crawler behavior (bot detection, JS rendering requirements) the way the live five sources have been through production runs. Before wiring any candidate into `site_configs.yaml`, re-check `robots.txt` and do a small discovery-only run first, following the pattern already used for tyomarkkinatori.fi's gap-crawl (see [crawler-improvements.md](../specs/crawler-improvements.md)).
