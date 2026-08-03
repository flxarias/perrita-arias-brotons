"""Persistencia: JSON versionado en git (la "base de datos") + export CSV a Sheets.

Se escribe con claves ordenadas y sangría fija para que cada ejecución nocturna
produzca un diff legible en git: el histórico del repositorio *es* el histórico
de la base de datos.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import Dog, dedupe_key
from .normalize import now_iso

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DOGS_JSON = DATA / "dogs.json"
META_JSON = DATA / "meta.json"
SHELTERS_JSON = DATA / "shelters.json"
CSV_PATH = DATA / "exports" / "dogs.csv"

SOURCE_PRIORITY = ["manual", "link", "kerubi", "miwuki", "reinasbiberon", "villena", "apadac", "anaa"]

CSV_COLUMNS = [
    "id", "score", "name", "sex", "age_months", "age_band", "birth_date", "size",
    "weight_kg", "breed", "breed_type", "ppp", "province", "location", "shelter",
    "status", "urgent", "good_with_kids", "sterilized", "vaccinated", "chipped",
    "source", "url", "photo", "first_seen", "last_seen", "description",
]


def load_criteria() -> dict:
    return json.loads((ROOT / "config" / "criteria.json").read_text(encoding="utf-8"))


def load_dogs() -> dict[str, Dog]:
    if not DOGS_JSON.exists():
        return {}
    raw = json.loads(DOGS_JSON.read_text(encoding="utf-8"))
    items = raw["dogs"] if isinstance(raw, dict) else raw
    return {d["id"]: Dog.from_dict(d) for d in items}


def load_meta() -> dict:
    if META_JSON.exists():
        return json.loads(META_JSON.read_text(encoding="utf-8"))
    return {"runs": [], "last_run": None, "new_ids": [], "counts": {}}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def merge(existing: dict[str, Dog], scraped: list[Dog]) -> tuple[dict[str, Dog], list[Dog], list[Dog]]:
    """Funde el barrido con lo ya guardado.

    Devuelve (base actualizada, altas nuevas, fichas modificadas).
    Nunca borra: lo que desaparece de la fuente se marca con `gone_since`.
    """
    now = now_iso()
    merged = dict(existing)
    new: list[Dog] = []
    changed: list[Dog] = []
    seen_ids: set[str] = set()

    for dog in scraped:
        seen_ids.add(dog.id)
        prev = merged.get(dog.id)
        if prev is None:
            dog.first_seen = dog.first_seen or now
            dog.last_seen = now
            dog.updated_at = now
            merged[dog.id] = dog
            new.append(dog)
            continue

        dog.first_seen = prev.first_seen or now
        dog.last_seen = now
        dog.gone_since = None
        if prev.entry in ("manual", "link") and dog.entry == "scraper":
            # una ficha editada a mano manda sobre el scraper, salvo estado y foto
            prev.last_seen = now
            prev.status = dog.status
            merged[dog.id] = prev
            continue
        if prev.content_hash != dog.content_hash:
            dog.updated_at = now
            changed.append(dog)
        else:
            dog.updated_at = prev.updated_at or now
        merged[dog.id] = dog

    # marcar bajas de las fuentes que sí se han barrido
    scraped_sources = {d.source for d in scraped}
    for did, dog in merged.items():
        if dog.source in scraped_sources and did not in seen_ids and not dog.gone_since:
            if dog.entry == "scraper":
                dog.gone_since = now
                dog.status = "no-disponible" if dog.status == "disponible" else dog.status

    return merged, new, changed


def annotate_duplicates(dogs: list[Dog]) -> None:
    """Marca fichas que parecen la misma perra en dos portales distintos."""
    groups: dict[str, list[Dog]] = {}
    for d in dogs:
        if d.name and d.name != "Sin nombre":
            groups.setdefault(dedupe_key(d), []).append(d)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda d: (SOURCE_PRIORITY.index(d.source) if d.source in SOURCE_PRIORITY else 99))
        primary = group[0]
        for dup in group[1:]:
            if "duplicada" not in dup.flags:
                dup.flags.append("duplicada")
            dup.score_breakdown["duplicada_de"] = primary.id


def save(dogs: dict[str, Dog], meta_update: dict) -> None:
    ordered = sorted(dogs.values(), key=lambda d: (-d.score, d.name.lower()))
    _write_json(
        DOGS_JSON,
        {
            "schema": 1,
            "generated_at": now_iso(),
            "count": len(ordered),
            "dogs": [d.to_dict() for d in ordered],
        },
    )
    meta = load_meta()
    meta.update(meta_update)
    runs = meta.get("runs", [])
    runs.append(
        {
            "at": meta_update.get("last_run", now_iso()),
            "new": len(meta_update.get("new_ids", [])),
            "changed": len(meta_update.get("changed_ids", [])),
            "total": len(ordered),
            "sources": meta_update.get("source_health", {}),
        }
    )
    meta["runs"] = runs[-90:]
    _write_json(META_JSON, meta)
    export_csv(ordered)


def export_csv(dogs: list[Dog]) -> Path:
    """CSV plano para Google Sheets (=IMPORTDATA sobre la URL raw de GitHub)."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        wr.writeheader()
        for d in dogs:
            row = d.to_dict()
            row["good_with_kids"] = d.traits.get("good_with_kids", "")
            for k in ("sterilized", "vaccinated", "chipped"):
                row[k] = d.health.get(k, "")
            row["description"] = (d.description or "").replace("\n", " ")[:500]
            wr.writerow(row)
    return CSV_PATH
