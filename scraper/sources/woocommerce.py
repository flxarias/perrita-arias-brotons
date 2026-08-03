"""Protectoras que publican sus fichas como productos de WooCommerce.

Es un patrón sorprendentemente común: la ficha del animal es un "producto" y la
Store API (/wp-json/wc/store/v1/products) la devuelve ya en JSON, sin parsear
HTML. Aquí se cubren Las Reinas del Biberón (Alicante, especialistas en
cachorros) y la Protectora de Villena.
"""
from __future__ import annotations

import re

from ..core import normalize as N
from ..core.http import get_json
from ..core.models import Dog, make_id
from .base import Source, SourceResult, register

# El nombre del atributo varía ("Sexo", "Fecha de nacimiento", "Talla"…), así que
# se busca por subcadena en orden: la primera coincidencia gana.
ATTR_MAP = [
    ("nacimiento", "birth"), ("birth", "birth"),
    ("sexo", "sex"), ("sex", "sex"), ("genero", "sex"),
    ("tamano", "size"), ("talla", "size"), ("size", "size"), ("porte", "size"),
    ("edad", "age"), ("age", "age"),
    ("raza", "breed"), ("breed", "breed"),
    ("peso", "weight"), ("weight", "weight"),
    ("altura", "height"),
]


def _slot_for(attr_name: str) -> str | None:
    k = N.key(attr_name)
    for needle, slot in ATTR_MAP:
        if needle in k:
            return slot
    return None


class WooSource(Source):
    """Base para cualquier tienda WooCommerce usada como catálogo de adopciones."""

    api_base: str = ""
    category_slugs: tuple[str, ...] = ()
    # muchas instalaciones etiquetan al mismo animal como Adoptar + Acoger +
    # Apadrinar, así que solo se descarta por especie o por estado final
    exclude_re = re.compile(r"^gat|-gat|adoptad|fallecid|reservad", re.I)
    default_province: str | None = None
    per_page: int = 50
    max_pages: int = 8

    def _categories(self) -> dict[str, int]:
        try:
            cats = get_json(f"{self.api_base}/products/categories?per_page=100")
        except Exception:
            return {}
        return {c["slug"]: c["id"] for c in cats}

    def _products(self, res: SourceResult) -> list[dict]:
        params = []
        cats = self._categories()
        ids = [str(cats[s]) for s in self.category_slugs if s in cats]
        for page in range(1, self.max_pages + 1):
            q = f"{self.api_base}/products?per_page={self.per_page}&page={page}"
            if ids:
                q += "&category=" + ",".join(ids)
            try:
                batch = get_json(q)
            except Exception as exc:
                self.log_error(res, f"página {page}: {exc}")
                break
            res.pages += 1
            if not batch:
                break
            params += batch
            if len(batch) < self.per_page:
                break
        return params

    def _to_dog(self, p: dict) -> Dog | None:
        name = p.get("name") or ""
        if not name:
            return None
        cat_slugs = {c.get("slug", "") for c in p.get("categories", [])}
        if any(self.exclude_re.search(s) for s in cat_slugs):
            return None
        if self.category_slugs and not (cat_slugs & set(self.category_slugs)):
            return None  # entradas de eventos, merchandising, donaciones…

        desc = N.clean_text(p.get("description") or "") + "\n" + N.clean_text(p.get("short_description") or "")
        attrs: dict[str, str] = {}
        for a in p.get("attributes", []) or []:
            slot = _slot_for(a.get("name", ""))
            if not slot:
                continue
            terms = a.get("terms") or []
            val = ", ".join(t.get("name", "") for t in terms) if terms else str(a.get("value", ""))
            if val:
                attrs[slot] = val

        # las categorías también aportan sexo/tamaño en muchas instalaciones
        for slug in cat_slugs:
            if not attrs.get("sex") and N.norm_sex(slug):
                attrs["sex"] = slug
            if not attrs.get("size") and N.norm_size(slug):
                attrs["size"] = slug

        sex = N.norm_sex(attrs.get("sex")) or N.norm_sex(self._field(desc, r"sexo"))
        weight = N.parse_weight(attrs.get("weight") or self._field(desc, r"peso"))
        # el peso declarado es mucho más fiable que la palabra suelta del texto
        size = (
            N.norm_size(attrs.get("size"))
            or N.size_from_weight(weight)
            or N.norm_size(self._field(desc, r"tama[ñn]o|talla|porte"))
        )
        birth = N.parse_birth_date(attrs.get("birth") or self._field(desc, r"nacimiento|f\.? ?nac"))
        age, age_est = N.parse_age_months(
            attrs.get("age") or self._field(desc, r"edad") or desc, with_flag=True
        )
        if birth:
            age, age_est = N.months_since(birth), False
        breed, breed_type = N.norm_breed(attrs.get("breed") or self._field(desc, r"raza"), desc)
        if N.looks_like_cat(breed, name, desc[:300]):
            return None

        photos = [im.get("src") for im in p.get("images", []) or [] if im.get("src")]
        status = "disponible"
        if re.search(r"adoptad[oa]", " ".join(cat_slugs) + " " + name, re.I):
            status = "adoptado"
        if re.search(r"\burgente\b", desc, re.I):
            status = "urgente"

        return Dog(
            id=make_id(self.slug, str(p.get("id") or p.get("slug"))),
            source=self.slug,
            source_label=self.label,
            url=p.get("permalink", ""),
            name=name,
            sex=sex,
            birth_date=birth,
            age_months=age,
            age_estimated=age_est,
            size=size,
            weight_kg=weight,
            breed=breed,
            breed_type=breed_type,
            province=self.default_province,
            location=self.default_province or "",
            shelter=self.label,
            shelter_url=self.home,
            photos=photos,
            description=desc,
            status=status,
        ).finalize()

    @staticmethod
    def _field(text: str, label_re: str) -> str:
        # el grupo no capturante es imprescindible: sin él la alternancia del
        # label se comería el resto del patrón
        m = re.search(rf"(?:{label_re})\s*[:\-–]\s*([^\n,;.]{{2,40}})", text, re.I)
        return m.group(1).strip() if m else ""

    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        res = self._result()
        products = self._products(res)
        if limit:
            products = products[:limit]
        for p in products:
            try:
                dog = self._to_dog(p)
                if dog:
                    res.dogs.append(dog)
            except Exception as exc:
                self.log_error(res, f"producto {p.get('id')}: {exc}")
        return res


@register
class ReinasBiberon(WooSource):
    slug = "reinasbiberon"
    label = "Las Reinas del Biberón"
    home = "https://www.lasreinasdelbiberon.org"
    api_base = "https://www.lasreinasdelbiberon.org/wp-json/wc/store/v1"
    default_province = "Alicante"
    provinces = ["Alicante"]
    # la misma tienda vende entradas a eventos y merchandising: solo interesan
    # las dos categorías bajo "peludos"
    category_slugs = ("individuo", "camada")


@register
class Villena(WooSource):
    slug = "villena"
    label = "SPAP Villena"
    home = "https://protectoravillena.com"
    api_base = "https://protectoravillena.com/wp-json/wc/store/v1"
    default_province = "Alicante"
    provinces = ["Alicante"]
    category_slugs = ("adoptar",)
