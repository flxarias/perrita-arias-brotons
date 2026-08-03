"""Extrae una ficha a partir de una URL suelta y la mete en la base de datos.

Lo usa el workflow `extract-link.yml`, que a su vez se dispara desde el panel
de administración de la web.

    python -m scraper.extract_link "https://…" [--browser] [--print]
"""
from __future__ import annotations

import argparse
import json
import sys

from .core import store
from .core.normalize import now_iso
from .core.scoring import score_dog
from .sources.generic import extract_from_url


def main() -> int:
    ap = argparse.ArgumentParser(description="Extraer una ficha desde un enlace")
    ap.add_argument("url")
    ap.add_argument("--browser", action="store_true", help="renderizar con Playwright (webs JS)")
    ap.add_argument("--print", dest="only_print", action="store_true", help="no guardar, solo mostrar")
    args = ap.parse_args()

    criteria = store.load_criteria()
    dog = extract_from_url(args.url, use_browser=args.browser)
    dog.entry = "link"
    dog.first_seen = dog.first_seen or now_iso()
    dog.last_seen = now_iso()
    dog.updated_at = now_iso()
    score_dog(dog, criteria)

    print(json.dumps(dog.to_dict(), ensure_ascii=False, indent=1))
    if args.only_print:
        return 0

    dogs = store.load_dogs()
    # si ya existe una ficha con esa URL, se actualiza en lugar de duplicar
    for existing in dogs.values():
        if existing.url and existing.url == dog.url:
            dog.id = existing.id
            dog.first_seen = existing.first_seen or dog.first_seen
            break
    dogs[dog.id] = dog
    store.annotate_duplicates(list(dogs.values()))
    store.save(dogs, {
        "last_run": now_iso(),
        "new_ids": [dog.id],
        "changed_ids": [],
        "source_health": {"link": {"ok": True, "dogs": 1, "errors": []}},
    })
    print(f"\nGuardada como {dog.id} (encaje {dog.score}/100)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
