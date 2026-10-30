# Provisional Field Mapping (FR-14)

The authoritative mapping is `backend/field_mapping.json` (version `provisional-mapping-v2`). It is explicitly provisional: the target names are placeholders (`PROVISIONAL_...`) until the complaint-system owner supplies the real field list, and it has not been validated against Salesforce or any production complaint system.

**One-to-one, checked.** Every column of a stored complaint (30) is either mapped to exactly one target field (23) or listed under `not_mapped` with the reason it is not part of the complaint record (7: `created`, `session_id`, `payload`, `summary_meta`, `scenario`, `is_poc`, `is_seed`). `backend/services/field_mapping.py` proves this (`check`), converts a record both ways without loss (`to_target`, `from_target`) and a test fails when a column is added without a decision. The save refuses a record that would leave a required target field empty. `GET /api/complaints/{id}/target` returns a saved complaint in the target structure; `GET /api/field-mapping` returns the mapping and whether it is one-to-one.

| PoC field | Provisional target field | Required |
| --- | --- | --- |
| `id` | `PROVISIONAL_ComplaintId` | yes |
| `customer_id`, `site_id`, `contract_id`, `order_id`, `container` | `PROVISIONAL_Account`, `_Site`, `_Contract`, `_Order`, `_Container` | no |
| `channel`, `registration_date`, `registering_user` | `PROVISIONAL_Channel`, `_RegistrationDate`, `_RegisteredBy` | yes |
| `status` | `PROVISIONAL_Status` | yes |
| `priority`, `owner_team`, `response_target_days` | `PROVISIONAL_Priority`, `_OwnerTeam`, `_ResponseTargetDays` | no |
| `original_text` | `PROVISIONAL_Description` (exactly as typed) | yes |
| `language`, `summary_json` | `PROVISIONAL_Language`, `_StructuredSummary` | no |
| `complaint_type`, `root_cause` | `PROVISIONAL_Type`, `_RootCause` | yes |
| `root_cause_category`, `other_reason` | `PROVISIONAL_RootCauseCategory`, `_OtherReason` | no (reason required when the cause is Other) |
| `repeat_detected`, `rule_version`, `taxonomy_version` | `PROVISIONAL_RepeatFlag`, `_RepeatRuleVersion`, `_TaxonomyVersion` | no |
