# Defaults per complaint type (FR-05)

Generated from `config.json` by `python -m scripts.defaults_doc`; a test fails when this file is out of date. Do not edit it by hand.

Status: **provisional**, to be confirmed by Complaint-system owner (last updated 2026-10-28). The values come from the typical complaints. They are refined later with the 12 months of real data (see below).

## The defaults

| Complaint type | Channel | Priority | Status | Owner team | Response target (days) |
|---|---|---|---|---|---|
| Collection service (`service`) | phone | normal | open | operations | 2 |
| Billing (`billing`) | email | normal | open | customer_service | 5 |
| Conduct / other (`conduct`) | phone | normal | open | customer_service | 3 |

Options: channel: phone, email, web, visit; priority: low, normal, high; owner team: operations, customer_service, sales.

## When they apply

- **Status and priority** apply as soon as the Review details step opens (the `_all` entry: status = open, priority = normal).
- **The rest** (owner team, response target and the type's own values) apply the moment a complaint type is chosen, or as soon as the assistant's suggested type is accepted. Choosing another type replaces the defaults that were not typed by hand.
- **Never over a value the employee typed or edited.** Those stay, whatever the type.
- **Channel follows how the complaint arrived**: **phone** when started from a search (the customer is on the phone) and **email** when started from a pasted email. The channel in the table is used only when the arrival is unknown (a direct API call).
- Every default is shown with the label *Default*, and the response target is stored with the complaint.

## Changing and refining them

- Edit `defaults` in `config.json`, or an administrator calls `PUT /api/config/defaults` (a new version and an audit entry are written). Then run `python -m scripts.defaults_doc` to update this file.
- `python -m scripts.field_profile --csv export.csv` reads the 12 months of real complaints (outside the app) and flags fields where one value covers at least 80% of the records: those are the default candidates.
