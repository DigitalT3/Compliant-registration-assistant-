# Provisional Field Mapping

The authoritative mapping is `backend/field_mapping.json`. It is explicitly provisional and has not been validated against Salesforce or any production complaint system.

| PoC field | Provisional target field | Requirement note |
| --- | --- | --- |
| `customer_id` | `PROVISIONAL_Account` | May be blank after no-match fallback. |
| `site_id`, `contract_id`, `order_id` | `PROVISIONAL_Site`, `PROVISIONAL_Contract`, `PROVISIONAL_Order` | Synthetic context references. |
| `channel`, `registration_date`, `registering_user` | `PROVISIONAL_Channel`, `PROVISIONAL_RegistrationDate`, `PROVISIONAL_RegisteredBy` | Channel is currently required; demo user is not a production identity. |
| `original_text`, `summary_json` | `PROVISIONAL_Description`, `PROVISIONAL_StructuredSummary` | Original text is retained as entered. |
| `complaint_type`, `root_cause`, `other_reason` | `PROVISIONAL_Type`, `PROVISIONAL_RootCause`, `PROVISIONAL_OtherReason` | Other reason is required when `other` is selected. |
| `repeat_detected` | `PROVISIONAL_RepeatFlag` | Deterministic rule result, not an AI decision. |
