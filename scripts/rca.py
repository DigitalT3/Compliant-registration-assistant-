"""FR-18 to FR-20 dry run on SYNTHETIC data: themes in "Other" reasons, a proposed shorter list, a re-label agreement check.

    python -m scripts.rca [--records 120] [--labelled 40] [--skip-relabel]

Uses the configured assistant (the live model when LLM_PROVIDER is set in .env, the mock otherwise) and the configured cause list.
It proves the tooling works and shows how the numbers are worked out. It is NOT acceptance evidence: the real checks need 12 months
of real "Other" text, the agreement of Kwafie, Naomi and Maikel, and 200 records labelled by experts. Nothing is saved.
"""
import argparse
import random
import time

from backend.services import ai, root_cause_analysis as rca
from backend.settings import get_config

THEMES = {   # invented "Other" reasons, English and Dutch; the real ones come from the complaint system
    "wildlife": ["A seagull built a nest under the lid of the container", "Mice were found in the paper container", "Een meeuw heeft een nest in de container gemaakt",
                 "Rats near the container area", "Vogels scheuren de zakken open"],
    "road closure": ["The road was closed for a street parade", "Weg afgesloten door een evenement, truck kon niet bij de container", "Roadworks closed the whole street for a week"],
    "legislation": ["Customer asks which regulation applies to their waste", "Vraag over de nieuwe wetgeving voor bedrijfsafval", "Question whether a permit is needed for this container"],
    "documents": ["Customer needs a certificate of disposal", "Waste declaration document was never sent", "Certificaat van vernietiging ontbreekt"],
    "smell": ["The neighbour complains about the smell from our container", "Buurman klaagt over stank bij de container", "Odour reported by the neighbours of the site"],
    "site visit": ["Customer wants a site visit to discuss the setup", "Verzoek om een bezoek ter plaatse", "Asks for an inspection walk-through"],
    "contact": ["Wrong contact person on file", "Telefoonnummer van de contactpersoon klopt niet", "Our email address in your system is wrong"],
    "sensor": ["The pilot sensor on the container shows wrong data", "Test unit with GPS was not removed", "Sensor battery empty after the pilot"],
}
NOISE = ["See attachment", "Please call me", "Unclear reason, customer upset", "Customer wants to speak to the manager about something else", "Zie bijlage"]
LABELLED = [   # (text, expert cause from the current list)
    ("The container was not emptied on Tuesday", "missed"), ("Collection missed again this week", "missed"), ("Onze container is niet geleegd", "missed"),
    ("The truck arrived hours late", "late"), ("Driver came after 6pm instead of the morning", "late"), ("Vuilniswagen kwam veel te laat", "late"),
    ("The container lid is broken", "damage"), ("Our bin was damaged by the truck", "damage"), ("Container is kapot na de ophaling", "damage"),
    ("Truck could not reach the container, blocked access", "access"), ("Gate was locked, driver left without emptying", "access"),
    ("We were charged twice on the invoice", "invoice"), ("Invoice shows the wrong price", "invoice"), ("Factuur klopt niet, dubbel gefactureerd", "invoice"),
    ("The driver was rude to our staff", "conduct"), ("Chauffeur was onbeleefd", "conduct"),
    ("Nobody told us about the changed collection day", "comms"), ("We were not informed about the schedule change", "comms"),
    ("Waste spilled on the road during emptying", "spillage"), ("Afval op straat gevallen bij het legen", "spillage"),
    ("The truck damaged our fence", "property_damage"), ("Lorry drove through the gate and broke it", "property_damage"),
    ("The weighed amount on the ticket is wrong", "weighing"), ("Gewicht op de weegbon klopt niet", "weighing"),
]


def synthetic(n, seed=7):
    rnd = random.Random(seed)
    pool = [(t, w) for t, ws in THEMES.items() for w in ws]
    rows = [rnd.choice(pool) for _ in range(int(n * 0.93))] + [("noise", rnd.choice(NOISE)) for _ in range(n - int(n * 0.93))]
    rnd.shuffle(rows)
    return [{"id": f"S{i:03d}", "text": text, "truth": t} for i, (t, text) in enumerate(rows)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=int, default=120)
    ap.add_argument("--labelled", type=int, default=40)
    ap.add_argument("--skip-relabel", action="store_true")
    a = ap.parse_args()
    cfg = get_config()
    print(f"assistant: {type(ai.get_provider()).__name__}; SYNTHETIC data, not acceptance evidence\n")
    recs = synthetic(a.records)
    t0 = time.time()
    th = rca.analyse_themes(recs, cfg)
    print(f"FR-18  {th['n']} 'Other' records -> {th['n_themes']} themes (>= {th['min_theme_size']} records each), "
          f"coverage {th['coverage']:.1%} (target {th['target']:.0%}, {'met' if th['meets_target'] else 'NOT met'}), "
          f"{th['mapped_to_existing']} mapped to an existing category, new categories: {th['new_categories']}  [{time.time() - t0:.0f}s]")
    for t in th["themes"][:12]:
        print(f"   {t['id']} {t['count']:>3}  {t['label']}  -> {t['existing_category'] or 'NEW: ' + str(t['new_category'])}")
    truth = {r["id"]: r["truth"] for r in recs}
    pure = sum(1 for t in th["themes"] if t["counts"] and len({truth[i] for i in t["record_ids"]}) == 1)
    print(f"   (synthetic check) themes holding one invented topic only: {pure} of {th['n_themes']}")
    t0 = time.time()
    p = rca.propose_list(th, cfg)
    print(f"\nFR-19  proposed list {p['version']}: {p['n_categories']} categories (today {p['current_size']}); shorter: {p['shorter']}; repairs needed: {len(p['repairs'])}  [{time.time() - t0:.0f}s]")
    for c in p["categories"]:
        print(f"   {c['id']}: {c['name_en']} | covers {len(c['covers_existing'])} causes, {len(c['covers_themes'])} themes | e.g. {'; '.join(c['examples'][:2])}")
    if not a.skip_relabel:
        old = {c["id"]: c for c in cfg["root_causes"]}
        keep = [(t, e) for t, e in LABELLED][: a.labelled]
        recs2 = [{"id": f"L{i}", "text": t, "expert": e} for i, (t, e) in enumerate(keep)]
        cats = [{"id": c["id"], "name_en": c.get("en"), "name_nl": c.get("nl"), "definition": c.get("definition"), "examples": c.get("examples")} for c in cfg["root_causes"]]
        t0 = time.time()
        r = rca.relabel(recs2, cats, [t["id"] for t in cfg["types"]])
        print(f"\nFR-20  {r['n']} labelled records re-labelled with the current list: agreement {r['agreement']:.1%} (target {r['target']:.0%} on {r['target_records']} records) -> {r['status']}"
              f"  [{time.time() - t0:.0f}s]  failed calls: {r['failed']}")
        for d in r["disagreements"][:5]:
            print(f"   expert {d['expert']} / assistant {d['assistant']}: {d['text']}")
    print("\nReminder: acceptance needs real data, the three process owners' agreement, and 200 expert-labelled records.")


if __name__ == "__main__":
    main()
