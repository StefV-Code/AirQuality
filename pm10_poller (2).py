"""
PM10 poller - Brussels real-time air quality (opendata.brussels.be)

Haalt de laatste 48u metingen op, en schrijft alleen NIEUWE metingen weg
naar een dagbestand (JSON Lines). Elk uur draaien = je bouwt eigen historiek op.

Gebruik:  python pm10_poller.py   (of gewoon runnen in Jupyter)
Geen extra packages nodig (enkel standaard Python 3).
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATASET = "real-time-air-quality-pm10-fine-particulate-matter"
URL = f"https://opendata.brussels.be/api/explore/v2.1/catalog/datasets/{DATASET}/exports/json"

# Map waar alles terechtkomt (de r vóór het pad is nodig op Windows!)
# Op GitHub Actions wordt PM10_BASE ingesteld; lokaal valt hij terug op je Eindwerk-map.
BASE = Path(os.environ.get(
    "PM10_BASE",
    r"C:\Users\vastm\OneDrive\Documents\Bureaublad\Syntra\Data-engineer 2026-2027\Eindwerk",
))

DATA_DIR = BASE / "data" / "raw" / "pm10"
STATE_FILE = BASE / "data" / "seen_fids.json"


def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def fetch() -> list:
    with urllib.request.urlopen(URL, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def record_key(r: dict) -> str:
    # 'fid' is NIET stabiel (bevat een tijdstempel van de bron-refresh),
    # dus we gebruiken station + meetmoment als unieke sleutel.
    return f"{r.get('ab_eoi_code')}|{r.get('timestamp')}"


def main() -> None:
    records = fetch()

    # Check: zitten de sleutelvelden erin? Zo niet, toon de velden zodat we kunnen aanpassen.
    if records and not {"ab_eoi_code", "timestamp"} <= records[0].keys():
        print("Let op: sleutelvelden ontbreken. Beschikbare velden:", list(records[0].keys()))
        return

    seen = load_seen()
    ingested_at = datetime.now(timezone.utc).isoformat()

    new = [r for r in records if record_key(r) not in seen]

    if new:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_file = DATA_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
        with out_file.open("a", encoding="utf-8") as f:
            for r in new:
                r["_ingested_at"] = ingested_at  # handig voor lineage
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        seen.update(record_key(r) for r in new)
        save_seen(seen)

    print(f"{ingested_at} | opgehaald: {len(records)} | nieuw: {len(new)}")
    print(f"Data staat in: {DATA_DIR}")


if __name__ == "__main__":
    main()
