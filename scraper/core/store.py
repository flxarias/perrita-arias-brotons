"""Persistencia: JSON versionado en git (la "base de datos") + export CSV a Sheets.

Se escribe con claves ordenadas y sangría fija para que cada ejecución nocturna
produzca un diff legible en git: el histórico del repositorio *es* el histórico
de la base de datos.
"""
from __future__ import annotations

import csv
import json
import re
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

# Cabeceras en castellano y valores legibles: esta hoja la abre la familia en
# Google Sheets, no un programa. Cualquier cambio aquí hay que replicarlo en
# assets/js/csv.js, que genera el mismo fichero desde el navegador.
CSV_COLUMNS = [
    "Encaje", "Nombre", "Sexo", "Edad", "Edad (meses)", "Etapa", "Nacimiento",
    "Tamaño", "Peso (kg)", "Raza", "Tipo de raza", "PPP",
    "Provincia", "Zona", "Localidad", "Protectora", "Tipo de protectora",
    "Estado", "Urgente", "Buena con niños", "Esterilizada", "Vacunada", "Con chip",
    "Duplicada", "Origen", "Alta", "Última revisión", "Ficha", "Foto", "Descripción", "Id",
]

_SI_NO = {True: "Sí", False: "No", None: ""}
_SEXO = {"hembra": "Hembra", "macho": "Macho"}
_TAMANO = {"mini": "Mini", "pequeno": "Pequeño", "mediano": "Mediano",
           "grande": "Grande", "gigante": "Gigante"}
_ETAPA = {"cachorro": "Cachorra", "joven": "Joven", "adulto": "Adulta", "senior": "Senior"}
_TIPO_RAZA = {"raza": "De raza", "mezcla": "Mezcla", "mestizo": "Mestiza",
              "desconocido": ""}
_ESTADO = {"disponible": "Disponible", "urgente": "Urgente", "reservado": "Reservada",
           "adoptado": "Adoptada", "acogida": "En acogida", "no-disponible": "Ya no aparece"}
_ZONA = {"core": "Alicante", "near": "Provincia vecina", "east": "Mitad este",
         "far": "Fuera de zona", "desconocido": ""}


def _edad_texto(meses: int | None, estimada: bool) -> str:
    if meses is None:
        return ""
    aprox = "~" if estimada else ""
    if meses < 1:
        return f"{aprox}Recién nacida"
    if meses < 24:
        return f"{aprox}{meses} {'mes' if meses == 1 else 'meses'}"
    años, resto = divmod(meses, 12)
    return f"{aprox}{años} años" + (f" y {resto} m" if resto else "")


def _limpio(texto: str | None) -> str:
    """Una sola línea, sin caracteres de control y sin espacios dobles."""
    if not texto:
        return ""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(texto))
    return re.sub(r"\s+", " ", t).strip()


def _numero(v) -> str:
    """Sin decimales inútiles: 15.0 → 15, 19.5 → 19.5."""
    if v in (None, ""):
        return ""
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)


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


def merge(
    existing: dict[str, Dog], scraped: list[Dog]
) -> tuple[dict[str, Dog], list[Dog], list[Dog], set[str]]:
    """Funde el barrido con lo ya guardado.

    Devuelve (base actualizada, altas, modificadas, ids vistos en este barrido).
    Aquí no se borra nada: lo que desaparece se marca con `gone_since` y de
    eliminarlo se encarga `purge_gone` en el siguiente barrido.
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

    return merged, new, changed, seen_ids


# Si una fuente falla a medias (una página de listado que no carga, un cambio de
# maquetación), de golpe "desaparecen" muchas fichas que en realidad siguen ahí.
# Por encima de este porcentaje se da por hecho que el fallo es nuestro y no se
# borra nada de esa fuente.
PURGA_MAX_PORCENTAJE = 0.4


def purge_gone(
    dogs: dict[str, Dog], scraped_sources: set[str], vistas: set[str]
) -> tuple[list[Dog], list[str]]:
    """Borra las fichas que ya no están en su web de origen.

    Se exige verlas ausentes **dos barridos seguidos**: en el primero `merge`
    les pone `gone_since` y en el segundo se eliminan. Un tropiezo puntual de
    una web no se lleva por delante una ficha buena, y a cambio se tarda un día
    más en limpiar lo ya adoptado.

    `vistas` son los ids que el barrido en curso sí ha encontrado.
    """
    borradas: list[Dog] = []
    avisos: list[str] = []
    # `merge` acaba de poner gone_since a las que faltan hoy: esas todavía no se
    # tocan. Solo se borra lo que ya venía marcado de un barrido anterior.
    hoy = now_iso()[:10]

    for source in scraped_sources:
        de_esta = [d for d in dogs.values() if d.source == source and d.entry == "scraper"]
        if not de_esta:
            continue
        candidatas = [
            d for d in de_esta
            if d.gone_since and d.gone_since[:10] < hoy and d.id not in vistas
        ]
        if not candidatas:
            continue

        proporcion = len(candidatas) / len(de_esta)
        if proporcion > PURGA_MAX_PORCENTAJE:
            avisos.append(
                f"{source}: {len(candidatas)} de {len(de_esta)} fichas ausentes "
                f"({proporcion:.0%}); parece un fallo de la fuente, no se borra nada"
            )
            for d in candidatas:
                d.gone_since = None  # se le da otra oportunidad
            continue

        for d in candidatas:
            dogs.pop(d.id, None)
            borradas.append(d)

    return borradas, avisos


# Una misma imagen repartida entre muchas fichas no es la foto de ninguna: es
# el logotipo de la protectora o su marcador de "sin foto". Dos fichas sí pueden
# compartirla legítimamente (hermanos de camada), tres ya no.
SHARED_PHOTO_LIMIT = 3
KNOWN_PLACEHOLDERS = ("img.miwuki.com/no-pic",)


def drop_shared_photos(dogs: list[Dog]) -> int:
    """Quita las imágenes genéricas y deja la siguiente foto buena de la ficha."""
    from collections import Counter

    # se cuenta solo la foto principal: las galerías arrastran ruido de la
    # plantilla y penalizarlas se llevaría por delante fotos buenas
    uses: Counter[str] = Counter(d.photo for d in dogs if d.photo)

    bad = {p for p, n in uses.items() if n >= SHARED_PHOTO_LIMIT}
    bad |= {p for d in dogs for p in d.photos if any(k in p for k in KNOWN_PLACEHOLDERS)}
    if not bad:
        return 0

    touched = 0
    for d in dogs:
        if not any(p in bad for p in d.photos) and d.photo not in bad:
            continue
        d.photos = [p for p in d.photos if p not in bad]
        if d.photo in bad:
            d.photo = d.photos[0] if d.photos else ""
        touched += 1
    return touched


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


def fila_csv(d: Dog, criteria: dict | None = None) -> dict:
    """Una ficha convertida a valores legibles por una persona."""
    from .normalize import geo_tier

    criteria = criteria or load_criteria()
    return {
        "Encaje": d.score,
        "Nombre": _limpio(d.name),
        "Sexo": _SEXO.get(d.sex or "", ""),
        "Edad": _edad_texto(d.age_months, d.age_estimated),
        "Edad (meses)": "" if d.age_months is None else d.age_months,
        "Etapa": _ETAPA.get(d.age_band or "", ""),
        "Nacimiento": d.birth_date or "",
        "Tamaño": _TAMANO.get(d.size or "", ""),
        "Peso (kg)": _numero(d.weight_kg),
        "Raza": _limpio(d.breed),
        "Tipo de raza": _TIPO_RAZA.get(d.breed_type, ""),
        "PPP": _SI_NO[bool(d.ppp)],
        "Provincia": d.province or "",
        "Zona": _ZONA.get(geo_tier(d.province, criteria), ""),
        "Localidad": _limpio(d.location),
        "Protectora": _limpio(d.shelter or d.source_label),
        "Tipo de protectora": _limpio(d.shelter_kind),
        "Estado": _ESTADO.get(d.status, d.status),
        "Urgente": _SI_NO[bool(d.urgent)],
        "Buena con niños": _SI_NO[d.traits.get("good_with_kids")],
        "Esterilizada": _SI_NO[d.health.get("sterilized")],
        "Vacunada": _SI_NO[d.health.get("vaccinated")],
        "Con chip": _SI_NO[d.health.get("chipped")],
        "Duplicada": _SI_NO["duplicada" in d.flags],
        "Origen": d.source_label or d.source,
        "Alta": (d.first_seen or "")[:10],
        "Última revisión": (d.last_seen or "")[:10],
        "Ficha": d.url,
        "Foto": d.photo,
        "Descripción": _limpio(d.description),
        "Id": d.id,
    }


def export_csv(dogs: list[Dog]) -> Path:
    """CSV para Google Sheets (=IMPORTDATA sobre la URL raw de GitHub).

    Se escribe con BOM y saltos CRLF para que Excel lo abra bien en español, y
    con todos los valores ya traducidos: nada de True/False ni de 'pequeno'.
    """
    criteria = load_criteria()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore",
                            quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        wr.writeheader()
        for d in sorted(dogs, key=lambda x: (-x.score, x.name.lower())):
            wr.writerow(fila_csv(d, criteria))
    return CSV_PATH
