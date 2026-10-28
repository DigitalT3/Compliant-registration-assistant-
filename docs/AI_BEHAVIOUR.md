# AI Behaviour and Fallback

## Modes

`backend/services/ai.py` selects a deterministic keyword-based mock provider unless `AI_PROVIDER=live` is configured. Mock responses are explicitly marked as mock in API results and the browser UI. The optional live provider is OpenAI-compatible and requires approved endpoint and credential settings; it was not exercised in the recorded verification.

## Operations and safeguards

The service supports structured summary generation, root-cause classification, and pasted-email extraction. Pydantic schemas validate summary fields and constrain classification to at most three configured taxonomy causes. Complaint text is handled as untrusted input, and repeat detection remains deterministic backend logic.

The configured threshold is `classification.min_confidence = 0.5`. Below it, the API returns no preselected cause. This value is provisional and does not represent a calibrated probability.

## Failure behaviour

Timeout, unavailable-provider, and malformed-output paths return a controlled failed AI status and are logged as AI events. The user keeps the original text and may finish the registration manually. Recorded integration tests cover these mock failure modes; they do not demonstrate live-provider resilience.
