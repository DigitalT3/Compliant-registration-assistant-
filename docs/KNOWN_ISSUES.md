# Known Issues and Handover Limitations

## Incomplete or unverified items

Live AI mode requires approved credentials and has not been tested. The deterministic mock provider demonstrates integration and fallback behaviour only; it is not evidence of summary quality, classification accuracy, calibrated confidence, or real-world performance.

The PoC uses a provisional taxonomy, field mapping, required-field set, defaults, and repeat rule. The dashboard calculates from recorded PoC events, but no real-user sessions, current-process baseline, or validated time-saving result exists. FR-18 through FR-20 remain later-phase work because no approved historical dataset or expert-labelled evaluation sample is available.

## Operational limits

SQLite and demo-role headers are suitable for local demonstration, not production deployment. Resetting data is destructive. There is no production-system integration, production authentication, external-mail ingestion, or formal compliance/security certification.
