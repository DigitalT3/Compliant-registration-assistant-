# End-to-end demo run (every user flow, in order)

Run this in the real app: real sign-in, live Claude, real clock. It covers all 42 flows of the flow list, in an order that works: each part leaves the data the next part needs. Tick as you go. Allow about 3 hours for the data entry and 45 minutes to present.

Accounts and customers are in `docs/USER_FLOWS_TEST.md`. Flow numbers in brackets point to that file.

## The 42 flows (what the item numbers mean)

The "Item" column in the tables below is the number of the flow in this list. Every number from 1 to 42 appears at least once, so no flow is left out.

**A. Sign-in and accounts**
1. Sign in, sign out, and the back button after sign-out
2. First sign-in with a temporary password forces a new password
3. Five wrong passwords lock the account
4. Users screen (admin): create an account, change role or function, deactivate, reset password
5. Role visibility: each role sees only its own menu items

**B. Registering a complaint (employee)**
6. Full registration end to end
7. Every way to find a customer: customer number, order, container, name, postcode, no match
8. Start from a pasted email
9. Prefill, defaults and field markers, including owner team and response target
10. Dutch and English
11. Summary: create, edit, billing fields
12. Classification: suggestions, no preselection when unsure
13. "Other" with a required reason, and the two-level cause picker
14. Going Back and forward between steps, step times with several visits
15. AI failure falls back to the manual form
16. Repeat check for all scenarios T10 to T20
17. Confirm or dispute a repeat link, with a reason
18. Unsaved registration: leave without saving, the abandoned view, and carrying on later

**C. Records and history**
19. History screen: list and open saved complaints
20. Audit Trail: records, search, record detail, the registration log, "Log incomplete" check
21. Unsaved registrations view
22. Exports: records, sessions, suggestions, disputes, employees, readout, labels sample, complaints extract

**D. Dashboard and reporting**
23. Dashboard as admin, with every panel
24. Lead sees only their team
25. By user group and By employee tables, minimum counts
26. Success criteria panel
27. Power BI panel and the reporting feed with its key
28. `python -m scripts.dashboard_check` agrees with the raw log

**E. Process owners and evaluation**
29. Root causes screen: agree with the cause list, agreement resets when it changes
30. Evaluation: blind labelling, usable or not usable
31. Evaluation: baseline stopwatch times and the user-test data
32. Exit interviews

**F. Rules, configuration and decisions**
33. Configuration: edit repeat rule values and the defaults per type
34. Rule sign-off by Juul (rule_owner), and admin sign-off not counting
35. Weekly review of disputed repeats
36. Readout: evidence, and go, adjust or stop decision by Glenn
37. Root-cause analysis on the 12-month data: themes, proposed list, three-owner agreement, re-label

**G. Customer data (admin)**
38. Customer data screens: customers, sites, contracts, orders and containers, including creating new ones

**H. Safety and technical checks**
39. Never touches the live complaint system: `scripts.readonly_check`
40. Access refused for the wrong role
41. Scripted checks: `scripts.repeat_check`, `requirements_check`, `classify_eval`, `summary_eval`, `email_eval`
42. About screen content

## Part 0. Prepare (before anyone watches)

1. Start: `API_PORT=8001 scripts/run_demo.sh`. Wait for "ready.", open http://127.0.0.1:5173.
2. Re-anchor the seeded repeat cases to today, once, on the demo day: `python -m backend.seed --reanchor`. T18 and T20 are only valid on this day.
3. Do **not** save anything for customers 100001, 100002, 100003, 100004, 100006, 100007, 100009, 100010, 100014, 100015, 100016 until Part 2 is done (saving changes what the repeat check finds).
4. Never register as `admin` when you want the data to count for employees; the admin appears as group "none".

## Part 1. Accounts and sign-in (items 1 to 5, 38)

| Step | Do | Expect | Item |
|---|---|---|---|
| 1 | Sign in as `admin@example.nl`, open **Users** | list of accounts with role and function | 4 |
| 2 | Create `juul@example.nl`, role **rule_owner**, a temporary password | account appears | 4 |
| 3 | Create a throwaway `lock.test@example.nl`, role employee, function sales | account appears | 4 |
| 4 | Sign out. Sign in as `juul@example.nl` with the temporary password | forced to choose a new password | 2 |
| 5 | Sign out. Try `lock.test@example.nl` with five wrong passwords | account locks for a while | 3 |
| 6 | Sign in as admin, **Users**: reset the password of `lock.test`, change its function, then deactivate it | each change shown; deactivated account cannot sign in | 4 |
| 7 | Sign out, press the browser Back button | no data, sign-in page | 1 |
| 8 | Sign in as each role in turn and read the menu: employee (Register, History, About), lead (adds Dashboard), evaluator (Root causes, Evaluation, Root-cause analysis), rule_owner (Configuration), admin (everything) | each role sees only its own items | 5 |
| 9 | As employee, try the Audit Trail address directly | refused | 40 |
| 10 | As admin, open **Customers**, create "Demo Recycling BV" (postcode 3011AA). Open **Sites**, **Contracts**, **Orders**, **Containers** and add one of each for it | new rows appear | 38 |
| 11 | Register as an employee and search "Demo Recycling" | the new customer is found with its site, contract, order | 38, 7 |

## Part 2. Repeat rule, without saving (item 16, flow 9)

Sign in as `employee1@example.nl`. For each row open Register, search the customer, choose the cause, go to **Repeat check and save** and read the result. **Do not save.**

| Case | Customer / site / cause | Expect |
|---|---|---|
| T10 | 100001, C001-S1, Missed collection | repeat, COM-SEED-1 |
| T11 | 100004, C004-S1, Missed collection | no repeat (different cause) |
| T12 | 100002, C002-S1, Missed collection | no repeat (80 days) |
| T13 | 100003, C003-S1, Missed collection | no repeat (cancelled) |
| T14 | 100006, C006-S1, Late collection | repeat, two links |
| T15 | 100007, C007-S2, Damage | no repeat (other site) |
| T16 | 100009, C009-S1, Missed collection | no repeat (other customer) |
| T17 | 100010, no site, Missed collection | no repeat; site missing |
| T18 | 100015, C015-S1, Invoice | repeat (exactly 60 days) |
| T19 | 100016, C016-S1, Invoice | no repeat (61 days) |
| T20 | 100014, C014-S1, Conduct | repeat (59 days) |

Also show `python -m scripts.repeat_check` (all cases pass).

## Part 3. Registering complaints (items 6 to 14, 17)

Always type the description by hand. Sign in as the employee named. These are saved.

| # | Employee | Customer / input | Description | What to show | Item |
|---|---|---|---|---|---|
| R1 | employee1 | search `100009` | The container at our depot was not emptied on Tuesday, it was missed again. | full flow: found in 2 s, prefilled fields marked, summary, 3 causes with reasons, repeat step, Save, ID like COM-00xx | 6, 9, 12 |
| R2 | employee1 | try each, do not save: `ORD-002-10`, `BOX-004-2`, `Delta Works`, `999999`, `1009ZZ` | (none) | order match, container match, pick list, "No customer found" with blank-and-flagged option, postcode | 7 |
| R3 | employee2 | Start from an email: paste the Marieke email from flow 3 | (taken from the body) | customer 100009 and container filled from the email | 8 |
| R4 | employee3 | search `100005` | Onze container is vandaag niet geleegd, de inzameling is gemist. | Dutch summary; then switch the interface to NL | 10 |
| R5 | employee2 | search `100018` | We were charged twice on the latest invoice. | type Billing, invoice fields in the summary; **edit the summary** before moving on (marker turns "edited") | 11, 12 |
| R6 | employee3 | search `100019` | Something odd happened but I am not sure what. | three causes, **none preselected** | 12 |
| R7 | employee1 | search `100020` | A seagull built a nest under the lid of our container. | choose **Other**: a reason is required; save is blocked without it; open the cause picker to show "Category > Cause" | 13 |
| R8 | employee1 | on any registration | (any) | change the complaint type on the details step: priority, owner team and response target change; edit one prefilled field, its marker becomes "edited" | 9 |
| R9 | employee2 | on any registration | (any) | click **Back** two times and go forward again: the log later shows 2 visits for that step | 14 |
| R10 | employee4 | search `100017`, pick the first site | The container was not emptied on Tuesday, it was missed again. | first of pair A: "No repeat" | 17 |
| R11 | employee5 | `100017`, same site | The container was not emptied on Tuesday, it was missed again. | second of pair A: repeat found, **Confirm** | 17 |
| R12 | employee6 | `100017`, same site | We were charged twice on the latest invoice. | first of pair B | 17 |
| R13 | employee7 | `100017`, same site | We were charged twice on the latest invoice. | repeat found; choose **Not a repeat** and type a reason (for example "Different invoice month") | 17 |

### Special runs (restart the app, then go back to normal)

- **AI failure (item 15, flow 13):** stop the app, start `AI_TIMEOUT_S=0.01 API_PORT=8001 scripts/run_demo.sh`, sign in as employee1, search `100011`, type a complaint. Expect: no suggestions, the plain form with prefill and defaults, the session marked in the log. Save it. Restart normally.
- **Abandoned registration (item 18, flow 12):** start `ABANDON_AFTER_MINUTES=1 API_PORT=8001 scripts/run_demo.sh`. As employee2 start a registration for `100012`, type the description, then wait over a minute without saving. Open the Audit Trail as admin, then **Unsaved registrations**: it is listed as abandoned with its log. Go back to the employee's screen and carry on: the registration resumes and saves (audit entry `session_resumed`). Restart normally.

## Part 4. Bulk data so the dashboard is full

Use `docs/USER_TEST_RUNBOOK.md` sample plan and the earlier plan: employee1 to employee8, 5 saved registrations each, all as the employee (40 in total). Mix so every figure has data:

- **Causes:** about 30 stay on the first suggestion, about 5 pick the 2nd or 3rd, 1 or 2 pick one outside the top 3.
- **Summary:** edit it in about 5.
- **Type:** change the suggested type in 2.
- **Seven categories:** one registration each for missed or late, container equipment (broken lid), spillage or property damage (gate), invoicing, weighing (weighbridge ticket too high), crew conduct (rude driver), communication (nobody called back).
- **"Other":** exactly 3 in total, each with a reason (R7 is one).
- **Groups:** customer_service (employee1, 4, 7), sales (employee2, 5, 8), site_operations (employee3, 6). All three groups must have registrations.
- **Repeat pairs:** R10 to R13 above give the repeat rate and the "Repeat rejected" column.
- **Prefill rate and step times:** automatic.

## Part 5. Records and history (items 19 to 22)

As admin:
1. **History**: list and open a saved complaint (19).
2. **Audit Trail**: search by record ID, customer name and number; open R1 (20). Show the record in the target structure, "How each field was filled", the registration log with time per step, the repeat check and the audit events. Show an edited summary reads "Summary Edited" and the log line "the suggested summary was changed (...)".
3. **Unsaved registrations** view (21).
4. **Exports** from Audit Trail and Dashboard: records, sessions, suggestions, disputes, employees, readout, labels sample, and the 12-month extract `/api/export/complaints-extract.csv` (22).

## Part 6. Process owners and evaluation (items 29 to 32)

1. **Root causes** (29): sign in as `kwafie@example.nl`, `naomi@example.nl`, `maikel@example.nl` in turn and choose "I agree with this list". "Agreed" appears only after all three. Then change the list as admin (config) and show that agreement resets.
2. **Blind labelling** (30): each of the three opens Evaluation and rates complaints as Usable or Not usable with their own cause (the saved cause and the suggestion are hidden). Reach 10 ratings, at least 8 usable.
3. **Baseline** (31): Evaluation, Baseline: enter stopwatch seconds for today's form, at least 3 per user group (for example 180, 240, 300 seconds).
4. **Exit interviews** (32): record 6 to 8, at least 5 yes, with a comment.

## Part 7. Rules, configuration and decisions (items 33 to 37)

1. **Repeat rule** (33): as `juul@example.nl`, Configuration: change the lookback (for example 60 to 90) and save. Any earlier sign-off stops counting. Change it back.
2. **Defaults per type** (33): show them on **About** (read only). Editing defaults is done through the administrator interface call `PUT /api/config/defaults` or in `config.json`; there is no edit screen. Say this openly in the demo.
3. **Sign-off** (34): admin clicks "Sign off this rule": recorded but does not count. Then Juul signs off: state "signed off".
4. **Weekly review** (35): as admin, Configuration: the banner "Weekly review due" with the disputes from R13; "Mark all as reviewed" with a note.
5. **Readout** (36): as admin (or a business-owner account for Glenn), Readout: evidence, open conditions, record Go, Adjust or Stop with a reason.
6. **Root-cause analysis** (37): as admin or an evaluator: Find themes, Propose a list, each of the three agrees, Re-label with the current list (fewer than 200 shows "indicative"). All on synthetic data and labelled that way.

## Part 8. Dashboard and reporting (items 23 to 28)

1. As admin, Dashboard (23): walk down every panel: tiles, Success criteria, By user group (all three groups, plus a "none" row from admin sessions if any remain), By employee (each with 5), rates, suggestion acceptance, root causes, step times, "Other" reasons.
2. As `lead.cs@example.nl` (24): only customer_service data.
3. **By user group / By employee** (25): point out the minimum of 3 saved per person and "indicative" below 10.
4. **Success criteria** (26): state each result against its target and its n.
5. **Power BI panel** (27): show the panel and the feed. In a terminal: `curl -s -H "X-Reporting-Key: $(grep ^REPORTING_TOKEN= .env | cut -d= -f2)" http://127.0.0.1:8001/api/reporting/sessions | head -c 600`. Say plainly that the Power BI report itself was not built.
6. `python -m scripts.dashboard_check --url http://127.0.0.1:8001 --email admin@example.nl` (28): every figure agrees with the raw log.

## Part 9. Safety and scripted checks (items 39 to 42)

```bash
python -m scripts.readonly_check
python -m scripts.requirements_check
python -m scripts.classify_eval
python -m scripts.summary_eval
python -m scripts.email_eval
python -m pytest tests -q
```

Open **About** (42): version, taxonomy, defaults and the provisional notice.

## Coverage map

| Items | Part |
|---|---|
| 1 to 5, 38, 40 | Part 1 |
| 16 | Part 2 |
| 6 to 15, 17, 18 | Part 3 |
| 19 to 22 | Part 5 |
| 23 to 28 | Part 8 |
| 29 to 32 | Part 6 |
| 33 to 37 | Part 7 |
| 39, 41, 42 | Part 9 |

## Say these openly in the demo

- Everything runs on synthetic data; targets in PRD section 4.3 are met only when real testers produce the numbers.
- The AI runs on Bedrock in us-east-2, not an EU region.
- Power BI: a feed and a script exist; the report was not built or opened.
- Defaults, causes and the repeat rule are drafts to be confirmed by their owners.
- FR-18 to FR-20 tools are proven on invented data only.
