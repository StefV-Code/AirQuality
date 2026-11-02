"""
Luchtkwaliteit poller - Brussels real-time air quality (opendata.brussels.be)

Haalt per polluent de laatste 48u metingen op, en schrijft alleen NIEUWE
metingen weg naar een dagbestand (JSON Lines) per polluent:
    data/raw/pm10/2026-11-02.jsonl
    data/raw/pm25/2026-11-02.jsonl

Een polluent toevoegen = één regel bijzetten in DATASETS hieronder.

Gebruik:  python pm10_poller.py   (of gewoon runnen in Jupyter)
Geen extra packages nodig (enkel standaard Python 3).
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# polluent -> dataset-naam op opendata.brussels.be
DATASETS = {
    "pm10": "real-time-air-quality-pm10-fine-particulate-matter",
    "pm25": "real-time-air-quality-pm25-fine-particulate-matter",
}

URL_TEMPLATE = "https://opendata.brussels.be/api/explore/v2.1/catalog/datasets/{}/exports/json"

# Map waar alles terechtkomt (de r vóór het pad is nodig op Windows!)
# Op GitHub Actions wordt PM10_BASE ingesteld; lokaal valt hij terug op je Eindwerk-map.
BASE = Path(os.environ.get(
    "PM10_BASE",
    r"C:\Users\vastm\OneDrive\Documents\Bureaublad\Syntra\Data-engineer 2026-2027\Eindwerk",
))

RAW_DIR = BASE / "data" / "raw"
STATE_DIR = BASE / "data" / "state"
OLD_PM10_STATE = BASE / "data" / "seen_fids.json"  # oude locatie (eerste versie)


def state_file(pollutant: str) -> Path:
    return STATE_DIR / f"seen_{pollutant}.json"


def migrate_old_state() -> None:
    # Eenmalig: het oude PM10-geheugen verhuizen naar de nieuwe plek.
    new = state_file("pm10")
    if OLD_PM10_STATE.exists() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        OLD_PM10_STATE.rename(new)
        print("Oud PM10-geheugen verhuisd naar", new)


def load_seen(pollutant: str) -> set:
    f = state_file(pollutant)
    if f.exists():
        return set(json.loads(f.read_text(encoding="utf-8")))
    return set()


def save_seen(pollutant: str, seen: set) -> None:
    f = state_file(pollutant)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def fetch(dataset: str) -> list:
    with urllib.request.urlopen(URL_TEMPLATE.format(dataset), timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def record_key(r: dict) -> str:
    # 'fid' is NIET stabiel (bevat een tijdstempel van de bron-refresh),
    # dus we gebruiken station + meetmoment als unieke sleutel.
    return f"{r.get('ab_eoi_code')}|{r.get('timestamp')}"


def poll(pollutant: str, dataset: str, ingested_at: str) -> None:
    records = fetch(dataset)

    # Check: zitten de sleutelvelden erin? Zo niet, toon de velden zodat we kunnen aanpassen.
    if records and not {"ab_eoi_code", "timestamp"} <= records[0].keys():
        print(f"[{pollutant}] Let op: sleutelvelden ontbreken. Velden:", list(records[0].keys()))
        return

    seen = load_seen(pollutant)
    new = [r for r in records if record_key(r) not in seen]

    if new:
        out_dir = RAW_DIR / pollutant
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with out_file.open("a", encoding="utf-8") as f:
            for r in new:
                r["_pollutant"] = pollutant      # handig als je later alles samenvoegt
                r["_ingested_at"] = ingested_at  # handig voor lineage
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        seen.update(record_key(r) for r in new)
        save_seen(pollutant, seen)

    print(f"{ingested_at} | {pollutant:<5} | opgehaald: {len(records)} | nieuw: {len(new)}")


def main() -> None:
    migrate_old_state()
    ingested_at = datetime.now(timezone.utc).isoformat()

    errors = 0
    for pollutant, dataset in DATASETS.items():
        try:
            poll(pollutant, dataset, ingested_at)
        except Exception as e:  # één kapotte bron mag de andere niet tegenhouden
            errors += 1
            print(f"{ingested_at} | {pollutant:<5} | FOUT: {e}")

    print(f"Data staat in: {RAW_DIR}")
    if errors == len(DATASETS):
        raise SystemExit("Alle bronnen faalden")  # dan krijg je een mail van GitHub


if __name__ == "__main__":
    main()
