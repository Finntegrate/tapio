# Tapio Evaluation Dataset Changelog

All notable changes to the Tapio RAG evaluation datasets are documented in this file.

## [1.1] - 2026-07-08

### Changed
- **Schema Format:** Migrated the entire `datasets/` folder from JSON Lines (`.jsonl`) to standard JSON arrays (`.json`) to improve linter support and code readability.
- **Citizenship Verification:** Corrected dead URLs in `citizenship.json` (`cz_003` / `cz_005`). Updated the golden targets to use `https://migri.fi/en/means-of-support` and `https://migri.fi/en/citizenship-application-for-adults`.
- **Kela Benefits:** Rewrote `kl_003` to reflect the 1 May 2026 social security reform, introducing the new **General Social Security Benefit** (*yleistuki*) and removing references to the abolished basic unemployment allowance (*peruspäiväraha*).

### Added
- **Taxation Evaluation:** Added `datasets/taxes.json` to evaluate RAG responses on residency classification (the 6-month rule) and the new 1 January 2026 key-employee 25% tax-withheld-at-source rate.
- **Housing Evaluation:** Added `datasets/housing.json` containing rental contract terms and Kela student housing allowance limits.
- **Healthcare Evaluation:** Added `datasets/healthcare.json` mapping public clinic access rights, student private insurance coverage minimums (€40k/€120k), and EHIC protocols.
- **Edge Cases:** Added `datasets/edge_cases.json` covering divorce transitions, pending work-permit rights, and the late 2024 inadmissible asylum-to-work permit changes.

---

## [1.0] - 2026-06-27

### Added
- **Initial Release:** Created basic taxonomy mappings (`domains.yaml`, `personas.yaml`, `policies.yaml`).
- **Core Datasets:** Launched baseline test sets for `residence_permits.jsonl`, `work_rights.jsonl`, `family_reunification.jsonl`, and `citizenship.jsonl`.
- **Retrieval Anchors:** Added initial baseline documents mapping to standard 2024/2025 Migri guidelines.
