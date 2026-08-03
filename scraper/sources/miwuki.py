"""Miwuki Pet Shelter — agregador con ~90.000 fichas de 4.800 protectoras.

Es la fuente más rentable de todas: muchas protectoras pequeñas de Alicante
(Drac4Paws, Mascotas de Zero, Las Reinas del Biberón, 7 Vidas Orihuela, AGA
Orihuela, Adoptamics, Alcoy…) publican aquí y en ningún otro sitio indexable.

Mecánica:
  1. GET del listado → token CSRF de Laravel.
  2. POST /busqueda-avanzada con los filtros → quedan guardados en la sesión.
  3. GET de la URL canónica con ?page=N y cabecera XHR → JSON {response.data.view}
     con el HTML del siguiente bloque de tarjetas.
  4. GET de cada /c/<id> para la ficha completa.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..core import normalize as N
from ..core.http import UA, get, post
from ..core.models import Dog, make_id
from .base import Source, SourceResult, register

BASE = "https://petshelter.miwuki.com"
ENTRY = f"{BASE}/perros-en-adopcion-en-alicante"
SEARCH = f"{BASE}/busqueda-avanzada"

# id de provincia en el formulario de Miwuki
PROVINCE_IDS = {
    "Alicante": "4", "Valencia": "48", "Murcia": "35", "Albacete": "3",
    "Castellón": "15", "Almería": "6", "Madrid": "32", "Barcelona": "9",
    "Tarragona": "45", "Zaragoza": "52", "Teruel": "46", "Cuenca": "18",
    "Ciudad Real": "17", "Toledo": "47", "Guadalajara": "20", "Jaén": "25",
    "Granada": "21", "Baleares": "8",
}


@register
class Miwuki(Source):
    slug = "miwuki"
    label = "Miwuki Pet Shelter"
    home = BASE
    kind = "agregador"
    provinces = ["Alicante", "Valencia", "Murcia", "Albacete", "Castellón", "Madrid"]

    def __init__(self, provinces: list[str] | None = None, sex: str = "H", max_pages: int = 12):
        self.target_provinces = provinces or ["Alicante", "Valencia", "Murcia", "Albacete", "Castellón"]
        self.sex = sex
        self.max_pages = max_pages

    # ------------------------------------------------------------------ listado
    def _session(self) -> tuple[requests.Session, str]:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
        r = get(ENTRY, session=s)
        r.raise_for_status()
        tok = BeautifulSoup(r.text, "lxml").select_one('input[name="_token"]')
        if not tok:
            raise RuntimeError("no se encontró el token CSRF de Miwuki")
        return s, tok["value"]

    def _listing_urls(self, res: SourceResult) -> list[str]:
        urls: list[str] = []
        for prov in self.target_provinces:
            pid = PROVINCE_IDS.get(prov)
            if not pid:
                continue
            try:
                s, token = self._session()
                r = post(
                    SEARCH, session=s,
                    data={
                        "_token": token, "fl_especie": "1", "fl_estado": "",
                        "fl_sexo": self.sex, "fl_size": "", "fl_pais": "ES",
                        "fl_provincia": pid,
                    },
                )
                r.raise_for_status()
                canonical = r.url
                found = self._cards(r.text)
                res.pages += 1
                for page in range(2, self.max_pages + 1):
                    rj = get(
                        f"{canonical}?page={page}", session=s,
                        headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
                    )
                    try:
                        view = rj.json()["response"]["data"]["view"]
                    except Exception:
                        break
                    chunk = self._cards(view)
                    res.pages += 1
                    if not chunk:
                        break
                    found += chunk
                urls += found
            except Exception as exc:  # una provincia caída no debe tumbar el barrido
                self.log_error(res, f"provincia {prov}: {exc}")
        return list(dict.fromkeys(urls))

    @staticmethod
    def _cards(html: str) -> list[str]:
        s = BeautifulSoup(html, "lxml")
        return [a["href"] for a in s.select("div.caso a[href*='/c/']") if a.get("href")]

    # ------------------------------------------------------------------ ficha
    def _detail(self, url: str) -> Dog | None:
        s = BeautifulSoup(get(url).text, "lxml")
        # la página tiene dos <h1>: el del animal y el de la protectora
        h1 = s.select_one(".info-mascota h1") or s.select_one("h1")
        if not h1:
            return None

        name = h1.get_text(strip=True)
        sex = None
        for i in h1.select("i[title]"):
            sex = N.norm_sex(i["title"]) or sex

        fields: dict[str, str] = {}
        for blk in s.select(".detalles > div"):
            lab = blk.select_one("span")
            if not lab:
                continue
            label = N.key(lab.get_text(strip=True))
            value = blk.get_text(" ", strip=True)
            value = value[: len(value) - len(lab.get_text(" ", strip=True))].strip()
            fields[label] = re.sub(r"\s+", " ", value)

        # El bloque de la edad no tiene etiqueta fija: cuando hay fecha de
        # nacimiento, la fecha *es* la etiqueta. Se prioriza siempre el dato
        # numérico ("1 años 5 meses") sobre la categoría ("Cachorro"), que solo
        # sirve como estimación de último recurso.
        birth = None
        age_months = None
        for label, value in fields.items():
            m = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", f"{label} {value}")
            if m:
                birth = N.parse_birth_date(m.group(1))
                age_months = N.parse_age_months(value) or N.months_since(birth)
                break
        if age_months is None:
            for label, value in fields.items():
                if label in ("raza", "peso", "tamano", "especie"):
                    continue
                if re.search(r"\d+\s*(años|anos|meses|semanas)", value, re.I):
                    age_months = N.parse_age_months(value)
                    if age_months is not None:
                        break

        size = N.norm_size(fields.get("tamano"))  # "Desconocido" cae a None a propósito
        weight = N.parse_weight(fields.get("peso"))
        breed_raw = fields.get("raza")

        # "¿Cómo soy?" y "Me entregan" son listas de etiquetas ya normalizadas
        traits = N.extract_flags(" . ".join(self._section_items(s, "como soy")), N.TRAIT_PATTERNS)
        health = N.extract_flags(" . ".join(self._section_items(s, "me entregan")), N.HEALTH_PATTERNS)

        story = self._section_text(s, "mi historia")

        photos = [
            a["href"] for a in s.select(".fotos a[href*='img.miwuki.com']") if a.get("href")
        ]
        main = s.select_one(".row img[src*='img.miwuki.com']")
        if main and main.get("src"):
            photos.insert(0, re.sub(r"/\d+$", "", main["src"]))

        loc_el = s.select_one(".info-mascota .info")
        location = loc_el.get_text(" ", strip=True) if loc_el else ""

        # el bloque .owner trae el nombre de la protectora y su tipo
        shelter, shelter_kind = "", ""
        owner = s.select_one(".owner .nombre h1")
        if owner:
            kind_el = owner.select_one("span")
            shelter_kind = kind_el.get_text(" ", strip=True) if kind_el else ""
            if kind_el:
                kind_el.extract()
            shelter = owner.get_text(" ", strip=True)
        shelter_a = s.select_one("a[href*='/l/']")
        shelter_url = urljoin(BASE, shelter_a["href"]) if shelter_a else ""
        if not shelter and shelter_url:
            shelter = shelter_url.rstrip("/").split("/")[-1].replace("-", " ").title()

        status = "disponible"
        if s.select_one(".estado.e2"):
            status = "urgente"
        elif s.select_one(".estado.e3"):
            status = "adoptado"
        elif s.select_one(".estado.e5"):
            status = "reservado"

        # la ficha suele repetir la edad en el relato ("es una hembra de 1 año y 5 meses")
        if age_months is None:
            age_months = N.parse_age_months(story)
        if age_months is None:
            age_months = N.parse_age_months(fields.get("edad", ""))

        breed, breed_type = N.norm_breed(breed_raw, story)
        if N.key(fields.get("especie", "perro")) not in ("perro", "") or N.looks_like_cat(breed, name):
            return None
        native = url.rstrip("/").split("/")[-1]

        return Dog(
            id=make_id(self.slug, native),
            source=self.slug,
            source_label=self.label,
            url=url,
            name=name,
            sex=sex,
            birth_date=birth,
            age_months=age_months,
            size=size,
            weight_kg=weight,
            breed=breed,
            breed_type=breed_type,
            location=location,
            province=N.norm_province(location),
            shelter=shelter,
            shelter_url=shelter_url,
            shelter_kind=shelter_kind,
            photos=photos,
            description=story,
            traits=traits,
            health=health,
            status=status,
        ).finalize()

    @staticmethod
    def _section_items(s: BeautifulSoup, heading_key: str) -> list[str]:
        for h2 in s.select(".contenido h2"):
            if N.key(h2.get_text(strip=True)).startswith(heading_key):
                box = h2.find_parent("div")
                if not box:
                    continue
                return [e.get_text(" ", strip=True) for e in box.select("div, li, span") if e.get_text(strip=True)]
        return []

    @staticmethod
    def _section_text(s: BeautifulSoup, heading_key: str) -> str:
        for h2 in s.select(".contenido h2"):
            if N.key(h2.get_text(strip=True)).startswith(heading_key):
                box = h2.find_parent("div")
                if box:
                    txt = box.get_text("\n", strip=True)
                    return re.sub(rf"^{re.escape(h2.get_text(strip=True))}\s*", "", txt)
        return ""

    # ------------------------------------------------------------------ api
    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        res = self._result()
        urls = self._listing_urls(res)
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
