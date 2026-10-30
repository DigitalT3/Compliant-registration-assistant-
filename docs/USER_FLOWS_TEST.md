# User flows to test in the real app (all functional requirements)

Run these in the real app: real sign-in, live Claude, no demo mode. Each flow says who signs in, what to do, what you should see, and which requirement it covers. Tick the "Pass" column as you go.

Start: `API_PORT=8001 scripts/run_demo.sh`, then open the address it prints. All customers and numbers below are in the synthetic data.

## Accounts

| Who | Sign in as | Role |
|---|---|---|
| Employee | `employee1@example.nl` (customer_service), `employee2@example.nl` (sales), `employee3@example.nl` (site_operations) | employee |
| Lead | `lead.cs@example.nl` | lead (sees customer_service only) |
| Process owners | `kwafie@example.nl`, `naomi@example.nl`, `maikel@example.nl` | evaluator |
| Administrator | `admin@example.nl` | admin (everything) |
| Rule owner (Juul) | create one in Users (role rule_owner) | rule_owner |
| Business owner (Glenn) | create one in Users (role business_owner), or use the admin | business_owner |

New accounts use a temporary password and ask for a new one at first sign-in.

## The clock

The real app runs on the real clock (`POC_CLOCK_MODE=real` in `.env`), so the "Checked" time and the saved record's timestamp are the real time. The synthetic dates were moved forward to today with `python -m backend.seed --reanchor` (adds and removes nothing; run it again on a later day to keep the seeded repeat cases in step, and it does nothing if already done that day).

Two scenarios in flow 9 sit right on the edge of the 60-day window and are only valid on the day you re-anchor: **T20** (59 days old, a repeat) and **T18** (exactly 60 days, a repeat only when the check runs before 12:00 that day). The others stay valid for weeks (T10 about 55 more days, T14 about 40) or indefinitely (the no-repeat cases). Run `python -m backend.seed --reanchor` on the test day. The automated tests check all eleven cases on a fixed clock and stay valid on any day (`python -m pytest tests/acceptance/test_repeat_fr12_13.py`).

## Order matters

Every saved complaint becomes history that the repeat rule can see. So:

1. Run flow 9 (repeat rule) first, before you save any complaint for customers 100001, 100002, 100003, 100004, 100006, 100007, 100009, 100010, 100014, 100015, 100016. In flow 9 you use the repeat check only and do not save.
2. Then run the saving flows. Save each scenario once, on the customer given.
3. If a repeat flag shows where this document says there should be none, check whether you saved an earlier complaint for the same customer, site and cause in the last 60 days.

## Flows

### 1. Register one complaint end to end (FR-01, 03, 04, 05, 07, 08, 09, 14, 15)
Sign in as `employee1@example.nl`. Register.
1. Type `100009` in the search field. Expect: the customer is found in 2 s or less, with its sites, active contracts and the last orders.
2. Use this customer. Expect: customer, site, contract, order, channel, date and registering user already filled, each marked "prefilled" or "default".
3. Describe: type `The container at our depot was not emptied on Tuesday, it was missed again.` Leave the field. Expect: a structured summary (what, where, when, impact) in English within about 3 s.
4. Classify. Expect: a suggested type and three causes, each with a one-line reason; "Missed collection" first.
5. Confirm and go to Repeat check and save. Expect: the repeat result (see flow 9), then Save.
6. Expect: a complaint ID like COM-0011 with no "POC" prefix.

### 2. Every way to find a customer (FR-01, 03, alternative flows)
| Type | Expect |
|---|---|
| `ORD-002-10` | customer 100002 found, matched via order number |
| `BOX-004-2` | customer 100004, site C004-S2, matched via container |
| `Delta Works` | two customers: a pick list, nothing chosen automatically |
| `999999` | "No customer found"; offers a search by name or postcode; you can continue with customer fields blank and flagged |
| a postcode such as `1009ZZ` | the customer for that postcode |

### 3. Start from an email (FR-02, Should)
Click "Start from an email" and paste:
```
Van: planning@zorgcentrumhetanker.example
Aan: klantenservice@renewi.example
Onderwerp: Container niet geleegd

Goedemorgen,

Onze container BOX-009-1 is vandaag niet geleegd. Klantnummer 100009. Graag een oplossing.

Groet,
Marieke
```
Expect: customer 100009 found, container BOX-009-1 filled, the complaint text taken from the body. The 10 sample emails are in `tests/acceptance/email_cases.json`; at least 8 of 10 should find the right customer (`python -m scripts.email_eval`).

### 4. Prefill, defaults and field markers (FR-04, 05, 06)
1. On the details step, change the complaint type. Expect: priority, owner team, response target, channel and status change to the defaults for that type; anything you typed yourself is not overwritten.
2. Edit a prefilled field. Expect: its marker changes to "edited".
3. Clear one optional field. Expect: marked blank.

### 5. Dutch and English (FR-07, language)
1. Describe in Dutch: `Onze container is vandaag niet geleegd, de inzameling is gemist.` Expect: Dutch summary, text stored exactly as typed.
2. Switch the interface to Dutch (NL). Expect: the whole interface in Dutch.

### 6. Summary (FR-08)
1. Customer `100018`, describe `We were charged twice on the latest invoice.` Expect: a billing summary with the invoice-type fields (invoice number, amount disputed), empty where the text does not say.
2. Edit the summary before saving. Expect: your edit is kept and marked as edited.

### 7. Classification (FR-09)
1. Customer `100018`, the invoice text above. Expect: type billing, causes led by the invoice cause, each with a reason, in 3 s or less.
2. Customer `100019`, text `Something odd happened but I am not sure what.` Expect: the top 3 shown with no pre-selection; you must choose.

### 8. "Other" and the two-level list (FR-10, 11)
1. Customer `100020`, text `A seagull built a nest under the lid of our container.` Choose "Other". Expect: it asks for a one-line reason and shows the closest category once more.
2. Try to save without a reason. Expect: blocked with a message.
3. Open the cause picker. Expect: causes shown as "Category > Cause".

### 9. Repeat rule (FR-12) — do this before saving the customers it uses
Open the repeat check for the customer, site and cause below, without saving.

| Case | Customer / site / cause | Expect |
|---|---|---|
| T10 | 100001, C001-S1, Missed collection | repeat, linked to COM-SEED-1 |
| T11 | 100004, C004-S1, Missed collection | no repeat (earlier one is a different cause) |
| T12 | 100002, C002-S1, Missed collection | no repeat (80 days ago, outside the window) |
| T13 | 100003, C003-S1, Missed collection | no repeat (earlier one is cancelled) |
| T14 | 100006, C006-S1, Late collection | repeat, two links: COM-SEED-6 and COM-SEED-7 |
| T15 | 100007, C007-S2, Damage | no repeat (different site) |
| T16 | 100009, C009-S1, Missed collection | no repeat (different customer) |
| T17 | 100010, no site, Missed collection | no repeat; shows the site is missing |
| T18 | 100015, C015-S1, Invoice | repeat (exactly 60 days, inclusive) |
| T19 | 100016, C016-S1, Invoice | no repeat (61 days) |
| T20 | 100014, C014-S1, Conduct | repeat (59 days) |

Each result shows the earlier complaint's date, status, cause and the reason it matched, plus the rule version. The script `python -m scripts.repeat_check` runs the same cases.

### 10. Confirm or dispute a repeat link, and the weekly review (FR-13)
1. As `employee1@example.nl`, register for 100001 / C001-S1 / Missed collection. On the repeat step, "Confirm" the link, and register a second case where you choose "Not a repeat". Expect: a reason is required to dispute (at least 3 characters).
2. Sign in as `admin@example.nl`, Configuration. Expect: a banner "Weekly review due" with the number of waiting disputes, and a table with your decision and its reason.
3. Click "Mark all as reviewed" with a note. Expect: the banner says up to date, and the table shows who reviewed and when.

### 11. Save and the Audit Trail (FR-14)
1. Sign in as `admin@example.nl`, Audit Trail. Expect: every saved record listed; search by record, customer name or number.
2. Open one. Expect: the record in the target field structure (names are placeholders), where each field came from, the repeat check, and its audit events.
3. Export records CSV. Expect: one row per record in the target structure.

### 12. The log per registration (FR-15)
1. While registering as an employee, watch the clock in the corner: it reads 00:00 until your first click or key press, then runs and shows time per step.
2. After saving, open the record in the Audit Trail. Expect: time per step that adds up to the total, fields prefilled or defaulted, the suggestions shown, and for each whether you kept or changed it.
3. Start a registration, leave without saving, then look at the unsaved registrations view. Expect: it is listed with its log.

### 13. Never touch the live complaint system, and the model-down fallback (FR-16, alternative flow)
1. Run `python -m scripts.readonly_check`. Expect: all rules pass (no client, address or write credential for the live complaint system).
2. Fallback: stop the app, start it with the AI switched off (leave `LLM_PROVIDER` empty), and register. Expect: the plain form with prefill and defaults, no suggestions, and the session marked in the log. Restart normally afterwards.

### 14. Dashboard (FR-17)
1. Sign in as `lead.cs@example.nl`. Expect: only the customer_service group's data.
2. Sign in as `admin@example.nl`, Dashboard. Expect: time per registration, "Other" share, suggestion acceptance (first cause, top 3, summary, type), repeat rate, each with a count (n), and a "By user group" split. Below 10 samples a figure is marked indicative.
3. Run `python -m scripts.dashboard_check`. Expect: every figure agrees with the raw log.

### 15. Process owners: cause list, ratings, baseline, exit interview (FR-08 target, FR-09 target)
1. Kwafie, then Naomi, then Maikel each open Root causes and choose "I agree with this list". Expect: "agreed" only after all three. Changing the list resets the agreement.
2. Each opens Evaluation, Blind labelling. Expect: the customer's text and the summary shown, but not the saved cause or the suggestion. Choose Usable or Not usable and, optionally, the cause. Expect the complaint to leave your list. "Usable summaries" shows the share against the 8-of-10 target.
3. Record a stopwatch time on Evaluation, Baseline, and an exit interview.

### 16. Repeat rule owner and the business owner (section 9, section 5)
1. As Juul (rule_owner), Configuration. Edit the lookback or cause level, save. Expect: any earlier sign-off no longer counts.
2. Click "Sign off this rule". Expect: state "signed off". An administrator's sign-off is recorded but does not count.
3. As Glenn (business_owner) or the admin, Readout. Expect: the evidence and open conditions, and a way to record go, adjust or stop with a reason.

### 17. Root-cause analysis on the 12-month data (FR-18, 19, 20)
Sign in as `admin@example.nl` or an evaluator, Root-cause analysis.
1. "Find themes". Expect: themes with counts, the category each maps to, the coverage figure against the 90% target, and a note that this is synthetic data.
2. "Propose a list". Expect: fewer categories than today, each with a definition and examples. Kwafie, Naomi and Maikel each agree; agreed only after all three.
3. "Re-label with the current list". Expect: it needs expert-labelled complaints; with fewer than 200 it says "indicative", never "met".

### 18. Access and security (non-functional)
1. As an employee, open the Audit Trail address. Expect: not offered in the menu, and refused if you go there directly.
2. Five wrong passwords on one account. Expect: the account locks for a while.
3. Sign out and use the browser's back button. Expect: no data without signing in again.

## Requirement coverage

| FR | Flows | FR | Flows |
|---|---|---|---|
| 01 | 1, 2 | 11 | 8 |
| 02 | 3 | 12 | 9 |
| 03 | 1, 2 | 13 | 10 |
| 04 | 1, 4 | 14 | 1, 11 |
| 05 | 4 | 15 | 12 |
| 06 | 4 | 16 | 13 |
| 07 | 1, 5 | 17 | 14 |
| 08 | 1, 6, 15 | 18 | 17 |
| 09 | 1, 7 | 19 | 17 |
| 10 | 8 | 20 | 17 |

The automated browser tests (`cd frontend && npm run test:e2e`, 57 cases) and `python -m pytest tests` (298 tests) run the same checks without a person; use them before each manual round.
