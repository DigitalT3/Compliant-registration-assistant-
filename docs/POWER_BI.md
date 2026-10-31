# Power BI for the dashboard (FR-17, the "Report" step)

The app has its own dashboard (Dashboard in the menu). This is the same data for Power BI, through a read-only feed. Nothing in it writes to the PoC.

## What is built
- `GET /api/reporting/workbook.xlsx`: all the tables in one Excel workbook (the dashboard button "Download Excel workbook for Power BI"; see `docs/POWER_BI_BROWSER.md` for the browser route, no Windows needed).
- `GET /api/reporting/<table>`: `group_summary`, `sessions`, `suggestions`, `employees`, `baseline`, `interviews`, `ratings`. CSV by default, `?format=json` for JSON. `?group=` and `?mode=` filter.
- `group_summary` carries the four FR-17 measures by user group, each with its sample size (n): mean time per registration, "Other" share, suggestion acceptance (first cause kept, cause within the top 3, summary kept, type kept) and repeat rate, plus an "All groups" row. It comes from the same code as the dashboard, so the figures match.
- Access: the header `X-Reporting-Key` (the value of `REPORTING_TOKEN` in `.env`; it can only read these tables, all teams), or a signed-in person with the analytics permission (a team lead sees their own team only, and not the baseline, interviews and ratings tables). Every read is written to the audit log (`reporting_read`).
- Files for Power BI: `docs/powerbi/dashboard.pq` (Power Query) and `docs/powerbi/measures.dax` (measures).

## Connect Power BI Desktop (on the computer that runs the app)
1. Start the app (`API_PORT=8001 scripts/run_demo.sh`).
2. Open `.local/powerbi.txt` for the key.
3. Power BI Desktop: Transform data > New Source > Blank Query > Advanced Editor. Paste `dashboard.pq`'s `fnReport` query, put the key in `Key`, and name the query `fnReport`.
4. Add one query per table (`= fnReport("group_summary")` and so on). If Power BI asks about credentials for the web source, choose Anonymous: the key is sent in the header. Close and apply.
5. Add the measures from `measures.dax`. Suggested report page:
   - cards: mean time, faster than baseline, "Other" share, top-3 accepted, repeat rate;
   - a table or clustered bar of `group_summary` by `group` (the FR-17 "by user group" view);
   - a card for summaries rated usable and for would use it daily.
6. Check: the numbers in `group_summary` should equal the app's Dashboard. `python -m scripts.dashboard_check` proves the app's figures against the raw log.

## Limits (be honest about these)
- Power BI Desktop on the same computer can reach `http://127.0.0.1:8001`. Power BI Service (the web) cannot: it needs a reachable address or a gateway, and the PoC has no hosting (see `docs/DEPLOY.md`). Hosting it is a Renewi decision, and the PRD keeps live integration and hosting out of scope.
- The Power Query and measure files were written to the Power Query and DAX syntax but have not been opened in Power BI here: there is no Power BI in this environment. Expect to adjust a column type or a measure when you first load them.
- The reporting key is a secret. Anyone with it can read the reporting tables (session and rating data; no complaint text). Do not commit it; `.env` and `.local/` are git-ignored. To rotate it, change `REPORTING_TOKEN` in `.env` and restart.
- Synthetic data only, as the PRD says for the build.
