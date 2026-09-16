# Planned guide network expansion — scope and build order

**Status:** Scoping (no build started)

**Owner:** Finntegrate

**Related:** [PRD §6, the guide network](../PRD.md#6-the-guide-network), [ADR 0005](../ADRs/0005-multi-agent-chat-experience.md), [multi-agent chat spec](multi-agent-chat.md), [issue #96](https://github.com/Finntegrate/tapio/issues/96), [grounding source research](../research/guide-network-grounding-sources.md)

## Purpose

PRD §6 lists seven guides on the public roster ([finntegrate.org/tapio](https://finntegrate.org/tapio/)) that are not yet implemented: Pellervo, Agricola, Louhi, Mielikki, Lempi, Ahti, Kokko. ADR 0005 requires a documented scope and routing test for every new guide "so that domains do not drift or overlap silently." This document is that scope, for all seven, plus a recommended build order. It is scoping work only — no agent code is introduced here.

Each entry below follows the same fields as the live guides in `backend/app/agents/definitions.py`: in-scope topics, an explicit out-of-scope boundary (naming which existing or planned guide owns the adjacent topic), and example queries a router should send here.

## Guide scopes

### Pellervo — The Harvest Guide (entrepreneurship)

- **In scope:** Registering a business (PRH, Business ID), light entrepreneurship / invoicing-service options, entrepreneur tax obligations at a general level, Business Finland and Elinvoimakeskus (formerly ELY Centre) startup support programs.
- **Out of scope:** Residence-permit eligibility or paperwork for entrepreneurs (Ilmarinen), job-seeking as an employee (Sampo), individual tax filing or accounting advice, benefits while starting a business (Rauni).
- **Example queries:** "How do I register a business as a foreigner in Finland?" · "What's the difference between light entrepreneurship and starting a company?" · "Are there grants for immigrant entrepreneurs?"

### Agricola — The Language Mentor (language and education)

- **In scope:** Finnish/Swedish language courses and integration training, foreign degree and qualification recognition, general education-system navigation (schools, universities, applying, credit transfer).
- **Out of scope:** Study-permit application paperwork (Ilmarinen), professional licensing exam content, employment matching (Sampo).
- **Example queries:** "Where can I study Finnish for free?" · "How do I get my foreign degree recognized in Finland?" · "What integration training am I entitled to?"

### Louhi — The Cultural Guide (customs and etiquette)

- **In scope:** Cultural norms and everyday etiquette, public holidays and their significance, general social expectations (e.g. punctuality, sauna culture, personal space).
- **Out of scope:** Legal rights adjacent to a custom (tenant rights stay with Otso, workplace norms with legal weight stay with Sampo), medical or mental-health topics (Mielikki, Lempi).
- **Example queries:** "Why do Finns value personal space?" · "What should I know about Finnish public holidays?" · "Is it normal to be invited to a sauna by coworkers?"
- **Resolved:** the [grounding source research](../research/guide-network-grounding-sources.md#louhi-culture-and-etiquette) settles the source-policy question this entry originally raised. InfoFinland and the statutory civic-orientation curriculum at yhteiskuntaorientaatio.fi (KEHA Centre, content from the Finnish Refugee Council and Finnish National Agency for Education) are as groundable as any other guide's sources — not merely curated cultural content.

### Mielikki — The Healer (healthcare navigation)

- **In scope:** Public healthcare system navigation (registering with a health center, appointments), health insurance (Kela health insurance, EU health insurance card), finding services (dental, maternity, occupational health), understanding fees and co-pays.
- **Out of scope:** Medical diagnosis or treatment advice, mental-health and wellbeing support (Lempi), Kela benefit payments not tied to health insurance (Rauni).
- **Example queries:** "How do I register with a local health center?" · "Does Kela cover my healthcare costs while my residence permit is pending?" · "Where can I find a dentist accepting new patients?"
- **Note:** Rauni's current out-of-scope line ("medical diagnosis and legal representation") anticipates this boundary. When Mielikki is built, Rauni's definition should be updated to name Mielikki as the handoff rather than leaving the boundary implicit.
- **Correction:** the [grounding source research](../research/guide-network-grounding-sources.md#mielikki-healthcare-navigation) found national rules (insurance eligibility, co-pay structure) are centralized via Kela/THL as assumed, but this guide's own example queries ("register with a local health center," "find a dentist accepting new patients") depend on service-level detail that lives with 21 wellbeing services counties plus Helsinki individually, not one centralized source. Treat that as a scoping decision for v1 (national rules only vs. also per-county service-finding), not an assumption that one crawl covers both.

### Lempi — The Wellbeing Supporter (mental health and community)

- **In scope:** Mental-health service navigation (public and NGO), general wellbeing resources, peer-support and community-connection pointers for newcomers.
- **Out of scope:** Crisis intervention or counseling itself, medical diagnosis, healthcare-system logistics (Mielikki keeps appointments and insurance).
- **Example queries:** "Where can I find low-cost mental health support in Helsinki?" · "Are there peer support groups for newcomers?" · "I'm feeling isolated — what community resources exist?"
- **Blocking dependency:** this domain is inherently crisis-adjacent. PRD §7.4 requires crisis-adjacent questions to be recognized and redirected to human or official support rather than answered directly, and that depends on the guardrail/escalation work in [#29](https://github.com/Finntegrate/tapio/issues/29) and the approved crisis-resource list in [#102](https://github.com/Finntegrate/tapio/issues/102). Lempi should not launch ahead of those.

### Ahti — The Navigator (transportation, utilities, banking)

- **In scope:** Public transport, opening a Finnish bank account, setting up utilities and internet, converting a foreign driving license, everyday registration logistics (postal address, DVV population information).
- **Out of scope:** Housing search or rental agreements (Otso), residence-document paperwork (Ilmarinen), benefits (Rauni).
- **Example queries:** "How do I open a Finnish bank account without a Finnish ID yet?" · "Can I use my foreign driving license in Finland?" · "How do I register my address with DVV?"
- **Note:** sources here are fragmented across many independent providers (individual banks, transit authorities, DVV) rather than one or two central authorities, unlike Migri/Kela/TE for the live guides. Corpus coverage should be checked before build.

### Kokko — The Regional Expert (municipal and regional)

- **In scope:** Municipality-specific services and contacts, region-specific integration programs, routing a user to the right local authority for their area.
- **Out of scope:** Anything with a single national authority already covered by another guide (permits, Kela, TE) — Kokko localizes, it doesn't duplicate national guidance.
- **Example queries:** "What immigrant services does Tampere offer?" · "Where's my nearest municipal employment service in Turku?" · "Does my municipality offer free language classes?" (the original second example referenced a "TE Office," which no longer exists as a physical entity — TE Office services transferred to 45 municipal employment areas on 1 January 2025)
- **Blocking dependency:** no existing corpus aggregates municipal-level content the way Migri/Kela/TE content is aggregated today, confirmed by the [grounding source research](../research/guide-network-grounding-sources.md#kokko-municipal-and-regional). The realistic path is the Suomi.fi Service Catalogue (PTV) Open API — a structured, CC0, nationally maintained data source — which reshapes this from a `crawler` source addition into an **ingest adapter** against a structured API, still outside this spec's scope but a different kind of backlog item than originally assumed.

## Recommended build order

| Order | Guide | Why here |
| --- | --- | --- |
| 1 | Agricola | Directly addresses the language-barrier problem PRD §2 opens with; sources are centralized and well established (OPH, Studyinfo, InfoFinland); no safety complications. |
| 2 | Mielikki | Healthcare is a near-universal early need; sources are centralized (Kela, THL, public healthcare portals); the "not medical advice" boundary is the same shape as a line Rauni already draws safely today. |
| 3 | Pellervo | Narrower audience (entrepreneurs only) than 1–2, but clean, centralized sources (PRH, Business Finland, Vero) and a boundary against Sampo already anticipated. |
| 4 | Ahti | Broad daily-life demand, but fragmented sources mean corpus coverage should be checked and likely expanded first, raising effort relative to 1–3. |
| 5 | Louhi | Broad demand, but blocked on a source-policy decision (what counts as groundable for cultural/etiquette answers) that should be resolved before build, not during it. |
| 6 | Lempi | Should not launch ahead of the guardrail/escalation work (#29) and an approved crisis-resource list (#102), since this domain is inherently crisis-adjacent per PRD §7.4. Build once those land, regardless of calendar order. |
| 7 | Kokko | Needs new per-municipality source aggregation (a `crawler`/`ingest` backlog dependency) before it can be grounded at all — the highest infrastructure dependency of the seven. |

Ranking basis: user demand (how many newcomers hit this need, and how early), source availability (whether centralized official sources already exist to ground answers), and blocking dependencies (safety or infrastructure work that has to land first regardless of demand).

**Open question:** the [grounding source research](../research/guide-network-grounding-sources.md#comparison-against-the-specs-build-order) found Mielikki's source picture is more fragmented than assumed above (§ Mielikki correction) and Louhi's blocking source-policy question is resolved, which — on source availability alone — would argue for moving Louhi up and Mielikki down. This table keeps the original demand-led order; whether to re-rank is a call for reviewers, not resolved by this document.

## Follow-up

A build issue for the top two guides (Agricola, Mielikki) is filed as a follow-on to [#96](https://github.com/Finntegrate/tapio/issues/96): see [#121](https://github.com/Finntegrate/tapio/issues/121).

The [grounding source research](../research/guide-network-grounding-sources.md) also found that Otso — already live — has no dedicated source in `crawler/tapio_crawler/config/site_configs.yaml`; InfoFinland and KKV would close that gap. That's independent of the seven guides scoped here and worth its own follow-on issue.
