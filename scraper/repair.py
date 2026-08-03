"""Aplica las reglas de limpieza a las fichas ya guardadas, sin volver a barrer.

Cuando se corrige un normalizador, las fichas antiguas siguen con el dato viejo
hasta que su fuente vuelve a barrerse. Esto las repasa todas en local: cuesta
segundos y no molesta a las webs de las protectoras.

    python -m scraper.repair --dry-run
    python -m scraper.repair
"""
from __future__ import annotations

import argparse

from .core import normalize as N
from .core import store
from .core.normalize import now_iso
from .core.scoring import score_dog


def main() -> int:
    ap = argparse.ArgumentParser(description="Repasa la base con las reglas actuales")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    criteria = store.load_criteria()
    dogs = store.load_dogs()
    cambios: dict[str, list[str]] = {"nombre": [], "estado": [], "descartadas": [], "foto": []}

    for did, d in list(dogs.items()):
        antes = (d.name, d.status, d.photo)

        if N.looks_like_listing(d.name) or N.looks_like_cat(d.breed, d.name, d.description[:300]):
            cambios["descartadas"].append(f"{d.source}/{d.name}")
            dogs.pop(did)
            continue

        nuevo = N.clean_name(d.name)
        if nuevo and nuevo != d.name:
            cambios["nombre"].append(f"{d.name} → {nuevo}")
            d.name = nuevo
        if N.ADOPTED_RE.search(antes[0]) and d.status != "adoptado":
            cambios["estado"].append(f"{d.name}: {d.status} → adoptado")
            d.status = "adoptado"

        d.photos = [p for p in d.photos if _foto_valida(p)]
        if d.photo and not _foto_valida(d.photo):
            d.photo = d.photos[0] if d.photos else ""
            cambios["foto"].append(f"{d.source}/{d.name}: {antes[2][:60]}")

    tocadas = store.drop_shared_photos(list(dogs.values()))
    for d in dogs.values():
        score_dog(d, criteria)
    store.annotate_duplicates(list(dogs.values()))

    print(f"fichas: {len(dogs)}")
    for k, v in cambios.items():
        print(f"  {k:12} {len(v)}")
        for x in v[:8]:
            print(f"      {x}")
    print(f"  imagen genérica quitada en {tocadas} fichas")

    if args.dry_run:
        print("\ndry-run: no se ha escrito nada")
        return 0

    store.save(dogs, {"last_run": now_iso(), "new_ids": [], "changed_ids": [],
                      "source_health": store.load_meta().get("source_health", {})})
    print("\nbase de datos actualizada")
    return 0


def _foto_valida(url: str) -> bool:
    # aquí NO se exige extensión: las URLs ya vienen de un adaptador y algunas
    # fuentes sirven las fotos sin ella
    from .sources.generic import is_junk_img

    return bool(url) and not is_junk_img(url)


if __name__ == "__main__":
    raise SystemExit(main())
