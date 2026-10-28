# Requirements Traceability

| ID | Status | Implementation and evidence | Limitation or confirmation needed |
| --- | --- | --- | --- |
| FR-01 | Tested | Lookup by customer, order, container, and name is implemented in `backend/services/lookup.py`; API tests cover T01-T05. | The recorded timing is isolated synthetic lookup, 10.46 ms; no production-data timing exists. |
| FR-02 | Tested | Mock email extraction is exposed by `POST /api/complaints/extract` and covered by integration tests. | Should requirement; no mailbox integration exists. |
| FR-03 | Tested | Customer context returns sites, active contracts, and up to ten orders. | Synthetic data only. |
| FR-04 | Tested | `backend/services/prefill.py` and the registration UI produce editable prefill. | Target-system field list is unconfirmed. |
| FR-05 | Tested | Configured channel defaults are applied without replacing manual values. | Defaults are provisional. |
| FR-06 | Tested | Provenance is returned and field events are recorded. | Enhanced visual conventions are PoC-level only. |
| FR-07 | Tested | Dutch and English text paths are covered by T06 and T07. | Language detection is heuristic in mock mode. |
| FR-08 | Tested | Schema-validated editable summaries are provided by the AI service. | Live-model quality is unverified. |
| FR-09 | Tested | Top-three candidate suggestions and low-confidence no-preselect behaviour are tested. | Mock confidence is not calibrated. |
| FR-10 | Tested | Save rejects `Other` without a reason in T09. | Taxonomy awaits approval. |
| FR-11 | Implemented | Root causes contain level-one and optional level-two values. | No independent two-level UX acceptance result. |
| FR-12 | Tested | Deterministic configurable repeat rule and seeded boundary cases are tested; browser flow shows `POC-SEED-1`. | Rule ownership and values require Juul confirmation. |
| FR-13 | Tested | Repeat disputes preserve original evidence and require a reason. | Could feature; no user evaluation has occurred. |
| FR-14 | Tested | PoC complaint save, retrieval, atomic rollback, and provisional field mapping are tested. | Mapping is not validated against Salesforce. |
| FR-15 | Tested | Sessions, step events, provenance, and suggestion outcomes feed backend metrics. | No real-user measurements exist. |
| FR-16 | Tested | Local SQLite-only persistence and no external write path are implemented. | This is not a formal security assessment. |
| FR-17 | Tested | Dashboard summary and filters read recorded data with sample sizes. | No meaningful dashboard outcome is implied without observed sessions. |
| FR-18 | Deferred | Synthetic `Other` reason grouping endpoint exists. | Approved 12-month historical data and analysis are absent. |
| FR-19 | Deferred | Taxonomy configuration can support later review. | No approved shorter taxonomy proposal exists. |
| FR-20 | Deferred | Evaluation endpoint records expert labels and agreement. | No 200-record real-data evaluation or expert agreement result exists. |
