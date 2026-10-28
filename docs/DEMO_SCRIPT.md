# Stakeholder Demo Script

## Preparation

Run `python -m backend.seed --reset`, start the backend and frontend, and select an employee demo user. State that the application uses synthetic data, a local PoC database, provisional business rules, and mock AI unless approved live credentials are configured.

## Demonstration

1. Search for customer number `100001` and select the displayed customer and site.
2. Show editable prefilled fields and the service complaint-type phone default.
3. Enter a missed-collection complaint, create the labelled mock summary, and edit it if desired.
4. Request root-cause suggestions, select Missed collection, and explain that low confidence never auto-selects a cause.
5. Continue to repeat checking and show seeded `POC-SEED-1` evidence.
6. Review and save the complaint; point out the PoC-only success message.
7. Open history and dashboard to show saved records and recorded metrics.
8. Explain that live AI quality, user acceptance, baseline time savings, approved taxonomy, and production integration remain outside the demonstrated evidence.
