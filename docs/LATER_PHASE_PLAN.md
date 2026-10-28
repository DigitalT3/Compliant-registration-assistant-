# Later-Phase Historical Taxonomy Plan

## Preconditions

Do not begin historical analysis until Renewi approves the dataset, lawful processing basis, hosting, access controls, retention, and reviewers. The initial PoC must remain synthetic-only.

## FR-18 to FR-20 path

First, import an approved historical `Other` dataset into a controlled analysis environment, validate its columns, and preserve source/version metadata. Next, group and review themes with process owners, record representative examples and coverage, and propose a shorter taxonomy for human approval. Finally, create an approved 200-record evaluation sample, collect expert labels, compare model and proposed taxonomy labels, calculate agreement with sample sizes, and review disagreements.

The current `/api/analysis/other-reasons` endpoint only groups stored synthetic reasons by normalized exact text. It is readiness support, not completion of historical clustering, taxonomy redesign, or expert agreement.
