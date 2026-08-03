"""Kerubi — portal de adopción con fichas muy limpias y filtro por provincia.

Cada ficha trae Raza / Sexo / F.Nacimiento / Tamaño en una tabla de detalles,
que es exactamente lo que necesita el scoring.
"""
from __future__ import annotations

import re

from ..core import normalize as N
from ..core.http import get, soup
from ..core.models import Dog, make_id
from .base import Source, SourceResult, register

BASE = "https://kerubi.es"
LISTINGS = {
    "Alicante": f"{BASE}/perros-en-adopcion-alicante/",
    "Valencia": f"{BASE}/perros-en-adopcion-valencia/",
    "Murcia": f"{BASE}/perros-en-adopcion-murcia/",
    "Madrid": f"{BASE}/perros-en-adopcion-madrid/",
    "Albacete": f"{BASE}/perros-en-adopcion-albacete/",
    "Castellón": f"{BASE}/perros-en-adopcion-castellon/",
}
DETAIL_RE = re.compile(r"/animales/perros-en-adopcion/[^/]+/?$")


@register
class Kerubi(Source):
    slug = "kerubi"
    label = "Kerubi"
    home = BASE
    kind = "agregador"
    provinces = list(LISTINGS)

    def __init__(self, provinces: list[str] | None = None):
        self.target_provinces = provinces or ["Alicante", "Valencia", "Murcia", "Albacete", "Castellón"]

    def _detail(self, url: str, hint_province: str | None) -> Dog | None:
        s = soup(url)
        title = s.select_one("h2[itemprop='name']") or s.select_one(".title-with-price h2")
        if not title:
            return None
        name = title.get_text(strip=True)
        if N.looks_like_listing(name):
            return None  # categorías y formularios de donación con plantilla de ficha

        # bloque "Detalles": <li> con .field-label y el valor al lado
        fields: dict[str, str] = {}
        for li in s.select(".categories-holder li, .key-details-holder li"):
            lab = li.select_one(".field-label")
            if not lab:
                continue
            label = N.key(lab.get_text(strip=True))
            whole = li.get_text(" ", strip=True)
            value = whole.replace(lab.get_text(strip=True), "", 1).strip(" : ")
            fields[label] = re.sub(r"\s+", " ", value)

        birth = N.parse_birth_date(fields.get("f nacimiento") or fields.get("fnacimiento", ""))
        age, age_est = N.parse_age_months(fields.get("edad", ""), with_flag=True)
        if birth:
            age, age_est = N.months_since(birth), False

        addr = s.select_one(".title-area address")
        location = addr.get_text(" ", strip=True) if addr else ""
        province = N.norm_province(location) or hint_province

        desc = ""
        holder = s.select_one(".description-holder, [itemprop='description']")
        if holder:
            for junk in holder.select("[class*='dpsp'], script, style, .element-title"):
                junk.decompose()
            desc = holder.get_text("\n", strip=True)
        if not desc:
            desc = " ".join(p.get_text(" ", strip=True) for p in s.select("article p")[:6])

        # la protectora aparece junto al enlace "Ver Protectora"
        shelter, shelter_url = "", ""
        link = s.find("a", string=re.compile(r"Ver Protectora", re.I))
        if link:
            shelter_url = link.get("href", "")
            box = link.find_parent(["div", "aside", "section"])
            if box:
                cand = [
                    t.strip() for t in box.get_text("\n", strip=True).split("\n")
                    if t.strip() and not re.search(r"ver protectora|donando|quiero ayudar", t, re.I)
                ]
                if cand:
                    shelter = cand[0][:60]

        # SOLO el carrusel de la ficha. La página trae además el avatar de la
        # protectora, el bloque "Animales similares" y widgets del pie: si se
        # cogen todas las <img>, las fotos de unos perros acaban en las fichas
        # de otros (una sola llegó a aparecer en 189 galerías).
        photos = []
        for img in s.select(".flexslider .slides img[src]"):
            src = img.get("src", "")
            if re.search(r"/wp-content/uploads/.+\.(jpe?g|png|webp)", src, re.I) and not re.search(
                r"logo|avatar|icon|placeholder|thumbnail", src, re.I
            ):
                photos.append(re.sub(r"-\d+x\d+(?=\.\w+$)", "", src))
        if not photos:
            og = s.select_one('meta[property="og:image"]')
            if og and og.get("content") and "logo" not in og["content"].lower():
                photos.append(og["content"])
        photos = list(dict.fromkeys(photos))[:8]

        breed, breed_type = N.norm_breed(fields.get("raza"), desc)
        native = url.rstrip("/").split("/")[-1]

        return Dog(
            id=make_id(self.slug, native),
            source=self.slug,
            source_label=self.label,
            url=url,
            name=name,
            sex=N.norm_sex(fields.get("sexo")),
            birth_date=birth,
            age_months=age,
            age_estimated=age_est,
            size=N.norm_size(fields.get("tamano")),
            weight_kg=N.parse_weight(fields.get("peso")),
            breed=breed,
            breed_type=breed_type,
            location=location or (province or ""),
            province=province,
            shelter=shelter,
            shelter_url=shelter_url,
            photos=photos,
            description=desc,
        ).finalize()

    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        res = self._result()
        pairs: list[tuple[str, str]] = []
        for prov in self.target_provinces:
            url = LISTINGS.get(prov)
            if not url:
                continue
            try:
                s = soup(url)
                res.pages += 1
                for a in s.select("a[href]"):
                    href = a["href"]
                    if DETAIL_RE.search(href):
                        pairs.append((href if href.startswith("http") else BASE + href, prov))
            except Exception as exc:
                self.log_error(res, f"listado {prov}: {exc}")

        seen: set[str] = set()
        uniq = [(u, p) for u, p in pairs if not (u in seen or seen.add(u))]
        if limit:
            uniq = uniq[:limit]
        for url, prov in uniq:
            try:
                dog = self._detail(url, prov)
                if dog:
                    res.dogs.append(dog)
            except Exception as exc:
                self.log_error(res, f"ficha {url}: {exc}")
        return res
