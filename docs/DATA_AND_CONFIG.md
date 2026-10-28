# Data and Configuration

## Synthetic dataset

`backend/seed.py` creates 22 fictional customers, connected sites, contracts, orders, containers, 15 seeded complaint records, demo users, and 20 scripted scenarios in `backend/seed_data/scenarios.json`. The fixed anchor date is `2026-10-28T12:00:00+00:00`, allowing repeat tests to remain deterministic.

Use `python -m backend.seed --reset` only when it is acceptable to delete the local PoC database. The command recreates and reseeds the database; it does not contact an external system.

## Configuration

`config.json` is the central configuration source. It defines the provisional taxonomy, defaults, required fields, demo users and permissions, seed clock, baseline placeholder, AI controls, and repeat-rule parameters. `backend/field_mapping.json` is a provisional one-to-one PoC-to-target mapping and explicitly states that it is not validated against Salesforce or another production system.

## Repeat rule

The default rule is enabled, has an inclusive 60-day lookback, matches `customer_id` and `site_id`, compares level-two root causes, includes `open` and `closed` history, and treats missing match fields as no match. The active rule version is `draft-juul-v1`. Every one of these business parameters is provisional pending confirmation from Juul and relevant Renewi owners.
