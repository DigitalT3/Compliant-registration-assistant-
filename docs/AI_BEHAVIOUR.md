# AI Behaviour and Fallback

## Modes

`backend/services/ai.py` selects a deterministic keyword-based mock provider unless `AI_PROVIDER=live` is configured. Mock responses are explicitly marked as mock in API results and the browser UI. The optional live provider is OpenAI-compatible and requires approved endpoint and credential settings; it was not exercised in the recorded verification.

## Operations and safeguards

The service supports structured summary generation, root-cause classification, and pasted-email extraction. Pydantic schemas validate summary fields and constrain classification to at most three configured taxonomy causes. Complaint text is handled as untrusted input, and repeat detection remains deterministic backend logic.

The configured threshold is `classification.min_confidence = 0.5`. Below it, the API returns no preselected cause. This value is provisional and does not represent a calibrated probability.

## Failure behaviour

Timeout, unavailable-provider, and malformed-output paths return a controlled failed AI status and are logged as AI events. The user keeps the original text and may finish the registration manually. Recorded integration tests cover these mock failure modes; they do not demonstrate live-provider resilience.


## Suggestion of type and causes: speed and measurement (FR-09)
- **What is suggested:** the complaint type and exactly three different root causes from the cause list, best first, each with a confidence and a one-line reason of at most 8 words (`prompts-v3`). Below `classification.min_confidence` nothing is preselected.
- **How the screen asks:** leaving *Describe complaint* the screen asks for the suggestion first (`/api/complaints/classify`) and shows the *Classify* step as soon as it is back; the summary (`/api/complaints/summarise`) is written alongside and fills in right behind it. Next and Save wait for the summary.
- **Speed, measured from a Mac in India against Claude Sonnet 4.6 in us-east-2** (`python -m scripts.classify_eval`): median 2.3 s, 28 of 30 within 3 s, slowest 3.6 s. About 1.2 s of every call is the network round trip to the region, the rest is the model writing about 190 tokens. With the Supabase database in Paris each suggestion adds about 0.8 s (three queries and the sign-in check at ~200 ms each): use the local server for timed sessions.
- **More margin** needs a nearer region or a faster model; the AWS account used here only allows the one Sonnet profile in us-east-2.
- **Top-3 acceptance** is recorded by the server at save: the suggestions shown (last `classify` event of the session) against the cause saved, as `classification_outcome` with `in_top3`. Target: at least 70% accepted within the top three, shown on the dashboard.
