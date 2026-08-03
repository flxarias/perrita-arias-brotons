"""APADAC — Protectora de Animales de Callosa de Segura (Alicante).

Publica cada ficha en /adopta/<slug> con una <dl> de datos perfectamente
etiquetada (Especie, Sexo, Edad, Tamaño, Raza, Zona, Energía, Cuidados).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from ..core import normalize as N
from ..core.http import soup
from ..core.models import Dog, make_id
from .base import Source, SourceResult, register

BASE = "https://protectora-apadac.org"
# páginas informativas que cuelgan de /adopta/ y no son animales
NOT_ANIMALS = {"estoy-listo", "proceso", "cuestionario", "requisitos", "faq", "contacto"}


@register
class Apadac(Source):
    slug = "apadac"
    label = "APADAC Callosa de Segura"
    home = BASE
    provinces = ["Alicante"]

    def _links(self, res: SourceResult) -> list[str]:
        urls: list[str] = []
        for listing in (f"{BASE}/?species=perro", f"{BASE}/adopta"):
            try:
                s = soup(listing)
                res.pages += 1
            except Exception as exc:
                self.log_error(res, f"listado {listing}: {exc}")
                continue
            for a in s.select("a[href]"):
                href = a["href"]
                m = re.search(r"/adopta/([a-z0-9\-]+)/?$", href)
                if m and m.group(1) not in NOT_ANIMALS:
                    urls.append(urljoin(BASE, href))
        return list(dict.fromkeys(urls))

    def _detail(self, url: str) -> Dog | None:
        s = soup(url)
        h1 = s.select_one("h1")
        if not h1:
            return None

        fields: dict[str, str] = {}
        for dt in s.select("dl dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                fields[N.key(dt.get_text(strip=True))] = dd.get_text(" ", strip=True)

        if N.key(fields.get("especie", "perro")) not in ("perro", "perra", ""):
            return None  # gatos fuera

        story = ""
        for h in s.find_all(re.compile("^h[23]$")):
            if N.key(h.get_text(strip=True)).startswith("historia"):
                parts = []
                for sib in h.find_all_next(["p", "h2", "h3"]):
                    if sib.name in ("h2", "h3"):
                        break
                    parts.append(sib.get_text(" ", strip=True))
                story = "\n".join(p for p in parts if p)
                break
        if not story:
            story = " ".join(p.get_text(" ", strip=True) for p in s.select("main p")[:6])

        photos = []
        for img in s.select("main img[src], article img[src]"):
            src = img["src"]
            if re.search(r"\.(jpe?g|png|webp)", src, re.I) and "logo" not in src.lower():
                photos.append(urljoin(BASE, src))

        zona = fields.get("zona", "Callosa de Segura")
        breed, breed_type = N.norm_breed(fields.get("raza"), story)
        age = N.parse_age_months(fields.get("edad", ""))
        if age is None and re.fullmatch(r"\d{1,2}", fields.get("edad", "").strip()):
            age = int(fields["edad"].strip()) * 12  # "5" son años en esta ficha

        cuidados = fields.get("cuidados", "")
        native = url.rstrip("/").split("/")[-1]

        return Dog(
            id=make_id(self.slug, native),
            source=self.slug,
            source_label=self.label,
            url=url,
            name=h1.get_text(strip=True),
            sex=N.norm_sex(fields.get("sexo")),
            age_months=age,
            size=N.norm_size(fields.get("tamano")),
            breed=breed,
            breed_type=breed_type,
            location=zona,
            province=N.norm_province(zona) or "Alicante",
            shelter=self.label,
            shelter_url=BASE,
            photos=list(dict.fromkeys(photos))[:8],
            description=story,
            health=N.extract_flags(cuidados, N.HEALTH_PATTERNS),
        ).finalize()

    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        res = self._result()
        urls = self._links(res)
        if limit:
            urls = urls[:limit]
        for u in urls:
            try:
                dog = self._detail(u)
                if dog:
                    res.dogs.append(dog)
            except Exception as exc:
                self.log_error(res, f"ficha {u}: {exc}")
        return res
