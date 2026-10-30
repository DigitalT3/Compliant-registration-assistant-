# Summary template and rating by the process owners (FR-08)

## What the assistant produces
When the employee leaves *Describe complaint*, the assistant returns a structured summary in the language of the text:

| Field | Content |
|---|---|
| What | what went wrong |
| Where | the site or place |
| When | the date or time |
| Impact | the consequence for the customer |
| Type-specific fields | service: expected vs. actual service date, container no. · billing: invoice no., amount disputed · conduct: who or vehicle (if known) |

Rules (prompt `prompts-v2`): a field the text does not state stays empty ("Not stated in the text"); numbers, amounts, dates and names are copied as written and never calculated. Every field is editable before saving, and a marker shows whether it is *Suggested*, *Edited* or *Typed* (FR-06). The text the customer wrote is stored unchanged next to the summary (FR-07).

## Rating: what "usable" means (provisional, Renewi to confirm)
**Usable** = you would save the summary in the complaint record as it is, or after a small edit (a word or a figure).
**Not usable** = it is wrong, misleading or misses what the customer said, so you would rewrite it.

## How the process owners rate
1. Each owner has an account with the **evaluator** role (the same accounts that agree the cause list).
2. *Evaluation → Blind labelling* shows saved test complaints: the text the customer wrote and the labelled summary. The saved cause and the assistant's suggestion are hidden.
3. Choose **Usable** or **Not usable** (nothing is pre-selected). Choosing the cause you would assign is optional. *Save label*. The complaint leaves your list.
4. One rating per person per complaint counts (the latest). The share is shown as *Usable summaries* on the Evaluation page, as the target "Summaries rated usable" on the dashboard, and on the Readout page.

**Target:** at least 8 of 10 usable (80%). It is evaluated over all ratings with the number of ratings shown; below 10 complaints the dashboard marks it as indicative.

## Checking the assistant before the owners rate
`python -m scripts.summary_eval --url http://127.0.0.1:8001 --email you@example.nl --out summaries.csv` runs the ten typical complaints (`tests/acceptance/summary_cases.json`) through the model with a real sign-in and checks language, filled and empty fields, the type-specific fields and that no figure was invented. `--out` writes a sheet (text, summary, empty *usable* column) the owners can fill in on paper or in a spreadsheet. This check is not the owners' rating.
