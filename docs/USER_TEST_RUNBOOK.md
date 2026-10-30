# Running the measurements (PRD section 4.3, 13 and FR-18 to FR-20)

The synthetic data shows that the tool works. These targets need real people, so this is how to run them. Nothing here changes the live complaint system.

## The targets and where each result appears

| # | PRD target | Who does it | In the app | Where the result shows |
|---|---|---|---|---|
| 1 | Time per registration: at least 50% faster than today's form, aim under 90 s | Testers register; an evaluator or administrator times today's form first | Evaluation, **Baseline** (stopwatch seconds per user group and scenario); then the testers register in the assistant | Dashboard, **Duration**, against the baseline, by user group |
| 2 | Share of "Other" under 10% in the test set | Testers | Registrations made in the assistant | Dashboard, **Other share** |
| 3 | Suggested cause accepted, at least 70% within the top 3 | Testers | The suggestion on the Classify step | Dashboard, **Suggestion acceptance**, "Cause within top 3" |
| 4 | Cause accuracy, at least 85% agreement with expert labels | Kwafie, Naomi, Maikel | Evaluation, **Blind labelling** (the saved cause and the suggestion are hidden) | Evaluation, agreement with the expert labels |
| 5 | Fields prefilled or defaulted, at least 70% | Testers | Nothing extra | Dashboard, prefill rate |
| 6 | Repeats flagged, 100% of seeded repeat cases | A builder | Scripted cases T10 to T20, `python -m scripts.repeat_check` | Script output |
| 7 | Testers who would use it daily, at least 5 of 6 to 8 | Facilitator | Evaluation, **Exit interview** | Evaluation and the Readout page |
| 8 | Summaries rated usable, at least 8 of 10 | Kwafie, Naomi, Maikel | Evaluation, **Blind labelling**, "Usable / Not usable" | Evaluation, **Usable summaries**; dashboard; Readout |

The Readout page gathers these for Glenn's go, adjust or stop decision.

## The clock

For the timed sessions the app must run on the real clock (`POC_CLOCK_MODE=real`), so every saved record carries its real time. With the fixed clock every record gets the same timestamp. After changing it, restart the app. Run `python -m backend.seed --reanchor` once on the day if the repeat scenarios are part of the test.

## Before the test day

1. **Clean database.** Run `scripts/run_usertest.sh`. It uses its own set of tables (schema `usertest`) with only the synthetic history, so earlier practice records can't skew the figures. Do not register practice complaints in it; practise in the normal data. See `docs/USER_TEST_DATABASE.md`.
2. **Local server for the timed sessions.** The hosted database adds about 190 ms per call from a laptop in India, and that delay would be counted in the times. Use `docs/LOCAL_SERVER.md` for the sessions themselves.
3. **Accounts** (Users screen, signed in as administrator):
   - one employee account per tester, with their function (customer service, sales or site operations);
   - one lead per group, with the same function;
   - evaluator accounts for Kwafie, Naomi and Maikel;
   - a rule owner account for Juul.
   Each person gets a temporary password and changes it at first sign-in.
4. **Check the assistant.** Run `python -m scripts.requirements_check`, `scripts.classify_eval` and `scripts.summary_eval` against the clean copy with the live model. Confirm the model answers within 3 s and the summaries look right.
5. **Freeze.** Agree the cause list and repeat rule values with the owners first (or note that the draft values are used), then do not change them during the test.
6. **Sample plan** (PRD section 13): 2 to 3 employees per user group, 3 groups, 5 complaints each, taken from the 10 scripted complaints.

## On the day

1. **Today's form first.** For each tester and scenario, time "show me how" on the current system with a stopwatch, and enter the seconds on the Baseline screen with the user group.
2. **The assistant, same people, same scenarios, within a week.** Tell each tester to register as they normally would. Each registration is linked to the tester through their own sign-in. Do not coach them on the suggestions.
3. **Exit interview.** After the last scenario, ask "would you use this daily?" and record yes or no with a comment.
4. **Blind labelling.** After the sessions, Kwafie, Naomi and Maikel label the saved complaints (cause, and usable or not usable for the summary) without seeing the saved cause or the suggestion.
5. **Export.** From the Dashboard, export the CSVs (sessions, suggestions, disputes) before anything else changes.

## Reading the results honestly

- Below 10 samples the dashboard marks a figure as indicative. Report the sample size with every percentage.
- Time is the capped time per step (600 s per visit), not raw clock time. Say so in the readout.
- "Usable" and "log complete" are provisional definitions until Renewi confirms them.
- Accuracy is the share of cases where the expert's cause is in the top 3 or the first choice. State which one you report.

## FR-18 to FR-20 on real data (after the DPA allows it)

What is built: themes with coverage, a proposed shorter list with three-owner agreement, and a re-label test. All of it has been run on invented data only.

What you need first:
- **The DPA decision** for using complaint data, and the source system confirmed (assumed Salesforce cases).
- **The 12-month extract** in this shape: complaint ID, type, cause, free text, timestamps, creator role, status. `GET /api/export/complaints-extract.csv` produces exactly these columns for the PoC data, so the real file can follow it.
- **200 historic complaints labelled by experts** for FR-20. Kwafie, Naomi and Maikel label them; the 85% check is run only on these.

Gaps to close before this can run on a real extract:
- There is no importer for a real extract yet. It would load the file into a separate analysis set, not into the PoC records, and keep real text out of the registration data.
- The blind labelling screen currently lists PoC complaints. It would need to list the 200 historic ones.
- Real data must stay in the EU. The assistant currently runs in us-east-2 with one allowed model; use the Azure EU tenant the PRD names (section 11.2) before real text goes anywhere.

## What cannot be claimed until this is done

The success criteria in PRD section 4.3 are met only when the numbers above come from real testers, real process owners and (for FR-18 to FR-20) real data. Until then the app reports them as "indicative" or "not yet measured", and the traceability notes say the same.
