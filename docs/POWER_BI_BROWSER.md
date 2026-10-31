# Power BI in the browser (no Power BI Desktop needed)

The PRD's "Report" step names Power BI. Power BI Desktop only runs on Windows, and the Power BI service in the browser cannot reach `localhost`. This route works on a Mac: the app writes its reporting tables into one Excel workbook, and the Power BI service imports that workbook as a dataset. You then build the report in the browser.

What it is, honestly: a **snapshot**. Each time you want fresh numbers you export again and replace the dataset. A live connection needs Power BI Desktop (Windows) and the feed described in `docs/POWER_BI.md`. This route has been tested up to the workbook (read back and checked); the Power BI steps below follow how the service works but were not run by me, because that needs your Microsoft work account.

## What you need

- A **work or school Microsoft account** that may use Power BI (for example a DigitalT3 or Renewi account). A personal Gmail or Outlook address cannot sign up for Power BI.
- To share a report with team leads, a Power BI Pro licence for you and for them, or a workspace on a Premium capacity. Without that, only you can see it.

## 1. Write the workbook

With the app running (`API_PORT=8001 scripts/run_demo.sh`):

```bash
python -m scripts.export_powerbi
```

It reads the same read-only feed Power BI would use, with the reporting key from `.env`, and writes `.local/powerbi/renewi_complaints_feed.xlsx` (the folder is git-ignored). It has one table per sheet: `group_summary`, `sessions`, `suggestions`, `employees`, `baseline`, `interviews`, `ratings`.

For a team lead's own copy: `python -m scripts.export_powerbi --group customer_service --out .local/powerbi/customer_service.xlsx`.

An empty table (for example `baseline` before any stopwatch time is entered) has one blank row, because an Excel table needs one. Power BI shows it as an empty row. It disappears as data arrives.

## 2. Import it into Power BI

1. Open https://app.powerbi.com and sign in with the work account.
2. **My workspace** (or a workspace you made) → **New** → **Upload a file** → **Local file** (in some versions: **Get data** → **Files** → **Local file**). Choose the `.xlsx`.
3. When asked how, choose **Import** ("Import Excel data into Power BI"), not "Upload to OneDrive".
4. A **semantic model** (dataset) with the seven tables appears in the workspace.
5. Open its menu (three dots) → **Create report** → **Start from scratch**.

## 3. Build the report (five pages)

Everything needed by FR-17 comes from the `group_summary` table, so the first four pages need **no DAX at all**: drag the fields in and, in the field well, set the aggregation (Average, Median, Maximum). The `group_summary` table has one row called **All groups** and one row per user group. Filter a card to the row you want with a visual filter on `group`.

| Page | Visuals | Fields |
|---|---|---|
| **1 Speed** | Cards for median and mean registration time; clustered bar of mean time by group; a card for the stopwatch baseline | `sessions[duration_s]` (Median, Average), `group_summary[mean_duration_s]` by `group`, `baseline[seconds]` (Average) |
| **2 Data quality** | Card "Other share" (target under 10%); bar of registrations by cause; table of Other share by group | `group_summary[other_share]` (filter group = All groups), `sessions[root_cause]` Count of `session_id`, `group_summary[group]`, `other_share` |
| **3 Suggestions** | Clustered bars by group for first cause kept, cause within top 3 (target 70%), summary kept, type kept | `group_summary[first_cause_kept]`, `top3_accepted`, `summary_kept`, `type_kept` by `group` |
| **4 Repeats and steps** | Card "Repeat rate"; bar of repeat rate by group; time per step | `group_summary[repeat_rate]`; `sessions[find_customer_s]`, `review_details_s`, `describe_complaint_s`, `classify_s`, `repeat_save_s` (Average each) |
| **5 People and test** | Table of employees (saved, median seconds, top 3, other share); card "would use it daily"; card "summaries rated usable" | `employees[...]`, `interviews[would_use_daily]` (Average), `ratings[usable]` (Average) |

Show the sample size next to each percentage: add `group_summary[duration_n]` and the `*_n` columns to the tables. Below 10 samples the report should say "indicative", as the app does.

### Optional measures (a little DAX)

If the **New measure** option is available in the report editor (Data pane → three dots on a table → New measure), these give single-number cards that match the app's definitions:

```
Saved registrations = CALCULATE ( COUNTROWS ( sessions ), sessions[status] = "saved" )
Median registration time (s) = MEDIAN ( sessions[duration_s] )
Baseline mean (s) = AVERAGE ( baseline[seconds] )
Faster than baseline = DIVIDE ( [Baseline mean (s)] - AVERAGE ( sessions[duration_s] ), [Baseline mean (s)] )
Other share = DIVIDE ( CALCULATE ( COUNTROWS ( sessions ), sessions[status] = "saved", sessions[root_cause] = "other" ), [Saved registrations] )
Repeat rate = DIVIDE ( CALCULATE ( COUNTROWS ( sessions ), sessions[status] = "saved", sessions[repeat] = 1 ), [Saved registrations] )
Summaries rated usable = DIVIDE ( CALCULATE ( COUNTROWS ( ratings ), ratings[usable] = 1 ), COUNTROWS ( ratings ) )
Would use it daily = DIVIDE ( CALCULATE ( COUNTROWS ( interviews ), interviews[would_use_daily] = 1 ), COUNTROWS ( interviews ) )
```

The "faster than baseline" figure should be at least 50%, the "Other" share under 10%, the usable share at least 80% and "would use it daily" at least 5 of 6 to 8 testers (PRD section 4.3).

Save the report (**File** → **Save**), then **Pin to a dashboard** the visuals you want on one screen.

## 4. Share with team leads

- **Share** the report or a dashboard with each lead's work address (needs the licences above).
- To keep a lead to their own team, give them a report built from their own file (`--group`), so they never receive another team's rows. Do not rely on hiding a page: everybody who can open the report can open the data behind it.

## 5. Refresh

A file imported this way does not refresh by itself. Export again, then upload the new file with the **same name** and choose **Replace**. The report keeps its visuals and shows the new numbers.

## What this does and does not give you

| | |
|---|---|
| Works on a Mac, in the browser | yes |
| Same figures as the dashboard in the app | yes, from the same read-only feed (check against `python -m scripts.dashboard_check`) |
| Live data | no, a snapshot you refresh by hand |
| Report file (`.pbix`) in the repository | no; the report is built in the browser and lives in your workspace |
| Reaches your computer's `localhost` directly | no, the service cannot |
