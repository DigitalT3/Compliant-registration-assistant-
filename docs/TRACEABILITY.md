# Requirements Traceability

| ID | Status | Implementation and evidence | Limitation or confirmation needed |
| --- | --- | --- | --- |
| FR-01 | Tested | Lookup by customer number, order, container, name and postcode in `backend/services/lookup.py`; API tests and browser cases T01-T05 (incl. ambiguous name and no-match then postcode). | Timing measured on synthetic data only; no production-data timing. |
| FR-02 | Tested | Mock email extraction (`POST /api/complaints/extract`) is wired into the UI ("Start from an email"): headers stripped, identifiers validated against the database, customer looked up; backend tests and browser case T21. | Should requirement; paste only, no mailbox integration. |
| FR-03 | Tested | Customer context returns sites, active contracts, and up to ten orders. | Synthetic data only. |
| FR-04 | Tested | `backend/services/prefill.py` prefills customer, site, contract, order, container (also from the most recent order at the site) and the registration fields; browser cases T01-T03. | Target-system field list is unconfirmed. |
| FR-05 | Tested | Defaults for channel, priority, owner team, response target and status per complaint type, never overwriting manual values; browser case T07. | Defaults are provisional. |
| FR-06 | Tested | Provenance (prefilled, default, suggested, manual, edited, blank) is shown per field and recorded at save; the prefill rate is computed from it. | Visual conventions are PoC-level only. |
| FR-07 | Tested | Dutch and English text paths; browser case T06 (Dutch text summarised in Dutch) and T24 (Dutch UI). | Language detection is heuristic in mock mode. |
| FR-08 | Tested | One `analyze` call returns an editable, schema-validated summary with per-type fields (invoice number, container, ...). Tested with the mock provider only. | Live-model quality is unverified. |
| FR-09 | Tested | Top-three candidate suggestions and low-confidence no-preselect behaviour are tested. | Mock confidence is not calibrated. |
| FR-10 | Tested | Save rejects `Other` without a reason; browser case T09 also shows that a type must be chosen when the cause has none. | Taxonomy awaits approval. |
| FR-11 | Tested | Two-level taxonomy (8 categories, 11 causes) stored at both levels; the picker shows "Category > Cause"; backend tests. | Draft taxonomy; needs Renewi approval. |
| FR-12 | Tested | Deterministic configurable repeat rule (category-level match by default) and seeded boundary cases; browser case T10 shows `POC-SEED-1`. | Rule ownership and values require Juul confirmation. |
| FR-13 | Tested | Confirm / not-a-repeat decision with a required reason in the UI; the stored dispute keeps the original rule evidence; backend tests and browser case T10. | Could feature; no user evaluation has occurred. |
| FR-14 | Tested | PoC complaint save, retrieval, atomic rollback, and provisional field mapping are tested. | Mapping is not validated against Salesforce. |
| FR-15 | Tested | Sessions (participant, scenario, mode), step events, provenance and suggestion outcomes feed the metrics; baseline timings and exit interviews are stored; CSV export. | No real-user measurements exist yet. |
| FR-16 | Tested | Local SQLite-only persistence and no external write path are implemented. | This is not a formal security assessment. |
| FR-17 | Tested | Dashboard evaluates the PRD targets with sample size and an "indicative" flag for n<10, groups by group/scenario/mode/participant; browser case T23. | Nothing meaningful is implied until real test sessions exist. |
| FR-18 | Deferred | Synthetic `Other` reason grouping endpoint exists. | Approved 12-month historical data and analysis are absent. |
| FR-19 | Deferred | Taxonomy configuration can support later review. | No approved shorter taxonomy proposal exists. |
| FR-20 | Partly | Blind labelling sample (hides cause and AI output), per-rater evaluations and agreement are implemented and tested on synthetic data. | No 200-record real-data evaluation or expert agreement result. |
