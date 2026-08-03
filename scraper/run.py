"""Orquestador del barrido.

    python -m scraper.run                    # barrido completo de todas las fuentes
    python -m scraper.run --source miwuki    # solo una fuente
    python -m scraper.run --limit 5 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .core import store
from .core.models import Dog
from .core.normalize import now_iso
from .core.scoring import is_notifiable, score_dog
from .sources import build_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-12s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("run")

DIGEST_PATH = store.DATA / "last_digest.json"


def run(selected: list[str] | None, limit: int | None, dry_run: bool, use_browser: bool) -> dict:
    criteria = store.load_criteria()
    sources = build_sources(selected, use_browser=use_browser)
    if not sources:
        log.error("ninguna fuente coincide con %s", selected)
        return {}

    scraped: list[Dog] = []
    health: dict[str, dict] = {}

    for src in sources:
        t0 = time.time()
        log.info("→ %s (%s)", src.label, src.slug)
        try:
            res = src.fetch(limit=limit)
        except Exception as exc:
            log.exception("fuente %s ha fallado por completo", src.slug)
            health[src.slug] = {"ok": False, "dogs": 0, "errors": [str(exc)[:200]], "seconds": 0}
            continue
        for dog in res.dogs:
            score_dog(dog, criteria)
        scraped += res.dogs
        health[src.slug] = {
            "ok": bool(res.dogs) or not res.errors,
            "dogs": len(res.dogs),
            "pages": res.pages,
            "errors": res.errors[:6],
            "seconds": round(time.time() - t0, 1),
        }
        log.info("   %s fichas en %.1fs (%s errores)", len(res.dogs), time.time() - t0, len(res.errors))

    existing = store.load_dogs()
    merged, new, changed = store.merge(existing, scraped)

    # rescorear todo: los criterios pueden haber cambiado desde el último barrido
    for dog in merged.values():
        score_dog(dog, criteria)
    store.annotate_duplicates(list(merged.values()))

    notifiable = [d for d in new if is_notifiable(d, criteria)]
    notifiable.sort(key=lambda d: -d.score)

    digest = {
        "at": now_iso(),
        "total": len(merged),
        "scraped": len(scraped),
        "new": [d.id for d in new],
        "changed": [d.id for d in changed],
        "notifiable": [
            {
                "id": d.id, "name": d.name, "score": d.score, "url": d.url,
                "sex": d.sex, "age_months": d.age_months, "size": d.size,
                "province": d.province, "shelter": d.shelter or d.source_label,
                "photo": d.photo, "breed": d.breed,
            }
            for d in notifiable
        ],
        "source_health": health,
    }

    if dry_run:
        log.info("dry-run: no se escribe nada en data/")
    else:
        store.save(
            merged,
            {
                "last_run": digest["at"],
                "new_ids": digest["new"],
                "changed_ids": digest["changed"],
                "source_health": health,
                "counts": {
                    "total": len(merged),
                    "disponibles": sum(1 for d in merged.values() if d.status == "disponible"),
                    "hembras": sum(1 for d in merged.values() if d.sex == "hembra"),
                    "cachorras": sum(
                        1 for d in merged.values()
                        if d.sex == "hembra" and (d.age_months or 999) <= 12
                    ),
                },
            },
        )
        DIGEST_PATH.write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("escrito %s (%s fichas) y %s", store.DOGS_JSON, len(merged), store.CSV_PATH)

    log.info("nuevas: %s · modificadas: %s · notificables: %s", len(new), len(changed), len(notifiable))
    for d in notifiable[:10]:
        log.info("   ★ %s (%s) %s · %s · %s", d.score, d.name, d.sex, d.province, d.url)
    return digest


def main() -> int:
    ap = argparse.ArgumentParser(description="Barrido de protectoras — Perrita Arias Brotóns")
    ap.add_argument("--source", action="append", help="slug de fuente (repetible)")
    ap.add_argument("--limit", type=int, help="máximo de fichas por fuente")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-browser", action="store_true", help="omite las fuentes que requieren Playwright")
    ap.add_argument("--list", action="store_true", help="lista las fuentes disponibles y sale")
    args = ap.parse_args()

    if args.list:
        for s in build_sources(None, use_browser=True):
            print(f"{s.slug:22} {s.kind:11} {'[browser] ' if s.needs_browser else '':10} {s.label}")
        return 0

    digest = run(args.source, args.limit, args.dry_run, not args.no_browser)
    return 0 if digest else 1


if __name__ == "__main__":
    raise SystemExit(main())
