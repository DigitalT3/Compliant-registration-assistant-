// Power BI Desktop > Home > Transform data > New Source > Blank Query > Advanced Editor.
// 1) Create ONE query named fnReport with this text. 2) Create one query per table (see the lines below) that calls it.
// The key is in .local/powerbi.txt (REPORTING_TOKEN in .env). The app must be running (API_PORT=8001 scripts/run_demo.sh).

// ---- Query: fnReport ----
let
    BaseUrl = "http://127.0.0.1:8001",
    Key     = "PASTE-THE-KEY-FROM-.local/powerbi.txt",
    fnReport = (name as text) as table =>
        let
            Source   = Csv.Document(Web.Contents(BaseUrl, [RelativePath = "api/reporting/" & name, Headers = [#"X-Reporting-Key" = Key]]),
                                    [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
            Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true])
        in
            Promoted
in
    fnReport

// ---- One query per table (name them exactly like this) ----
// group_summary = fnReport("group_summary")   // the FR-17 measures by user group (first row "All groups")
// sessions      = fnReport("sessions")        // one row per registration: duration and seconds per step
// suggestions   = fnReport("suggestions")     // one row per field: accepted / changed / typed / empty
// employees     = fnReport("employees")       // how each employee registers
// baseline      = fnReport("baseline")        // stopwatch times on today's form
// interviews    = fnReport("interviews")      // exit interviews (would_use_daily 1/0)
// ratings       = fnReport("ratings")         // summary ratings by the process owners (usable 1/0)

// ---- Optional: make the group_summary numbers numeric (add as a second step of the group_summary query) ----
// = Table.TransformColumnTypes(fnReport("group_summary"), {
//     {"sessions", Int64.Type}, {"saved", Int64.Type}, {"mean_duration_s", type number}, {"duration_n", Int64.Type},
//     {"other_share", type number}, {"repeat_rate", type number}, {"first_cause_kept", type number},
//     {"top3_accepted", type number}, {"summary_kept", type number}, {"type_kept", type number}}, "en-US")
