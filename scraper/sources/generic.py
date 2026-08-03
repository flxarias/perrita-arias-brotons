"""Extractor genérico: convierte *cualquier* URL de ficha en un registro.

Es la pieza que da servicio a la "extracción automatizada a partir de enlaces"
del panel de administración, y también el plan B cuando una protectora no tiene
adaptador propio. Va probando de lo más fiable a lo más heurístico:

  1. JSON-LD (schema.org Product / Article)
  2. Metadatos OpenGraph
  3. Pares etiqueta/valor en <dl>, <table> o "Sexo: Hembra"
  4. Texto libre + normalizadores (edad, sexo, tamaño, raza, provincia)
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..core import normalize as N
from ..core.http import get
from ..core.models import Dog, make_id

LABELS = {
    "sex": r"sexo|g[ée]nero|sex",
    "size": r"tama[ñn]o|talla|porte|size",
    "age": r"edad|age",
    "birth": r"nacimiento|f\.?\s*nac|fecha de nacimiento|birth",
    "breed": r"raza|breed",
    "weight": r"peso|weight",
    "location": r"zona|ubicaci[óo]n|localidad|provincia|municipio|location|d[óo]nde",
    "shelter": r"protectora|asociaci[óo]n|refugio|shelter|entidad",
}

NOISE = re.compile(
    r"cookie|acepto|pol[íi]tica de privacidad|iniciar sesi[óo]n|newsletter|suscr[íi]bete|"
    r"todos los derechos|aviso legal|men[úu] principal",
    re.I,
)

# títulos de plantilla que no son el nombre del animal
GENERIC_TITLE = re.compile(
    r"(animal|pet|dog|perro|ficha|adoption|adopcion|detail|page|inicio|home|"
    r"sin titulo|untitled)([ ]?(detail|page|ficha|en adopcion))*"
)


def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el is not None else ""


def _labeled_pairs(s: BeautifulSoup) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for dt in s.select("dl dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            pairs[N.key(dt.get_text(strip=True))] = dd.get_text(" ", strip=True)
    for tr in s.select("table tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) == 2:
            pairs[N.key(cells[0].get_text(strip=True))] = cells[1].get_text(" ", strip=True)
    # patrón "Etiqueta" seguida de su valor en el hermano siguiente (muy común en temas WP)
    for label_re in LABELS.values():
        for node in s.find_all(string=re.compile(rf"^\s*({label_re})\s*:?\s*$", re.I)):
            parent = node.parent
            if not parent:
                continue
            nxt = parent.find_next_sibling()
            if nxt:
                val = nxt.get_text(" ", strip=True)
                if val and len(val) < 80:
                    pairs.setdefault(N.key(str(node)), val)
    return pairs


def _inline_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for slot, label_re in LABELS.items():
        m = re.search(rf"\b({label_re})\s*[:\-–]\s*([^\n|•·,;]{{1,60}})", text, re.I)
        if m:
            out[slot] = m.group(2).strip()
    return out


def _jsonld(s: BeautifulSoup) -> dict:
    for tag in s.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type") in ("Product", "Article", "BlogPosting", "Pet"):
                return node
    return {}


def _main_text(s: BeautifulSoup) -> str:
    for tag in s(["script", "style", "nav", "footer", "header", "form", "aside", "noscript"]):
        tag.decompose()
    root = s.select_one("main, article, .entry-content, .single-content, #content") or s
    lines = [ln.strip() for ln in root.get_text("\n", strip=True).split("\n")]
    keep = [ln for ln in lines if ln and not NOISE.search(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep))[:5000]


JUNK_IMG = re.compile(r"logo|icon|avatar|placeholder|sprite|favicon|/theme|/assets/ui", re.I)


def _images(s: BeautifulSoup, base: str) -> list[str]:
    urls: list[str] = []
    og = s.select_one('meta[property="og:image"]')
    # el og:image de muchas webs es el logotipo de la entidad, no el animal
    if og and og.get("content") and not JUNK_IMG.search(og["content"]):
        urls.append(urljoin(base, og["content"]))
    for img in s.select("main img[src], article img[src], .entry-content img[src], img[src]"):
        src = img.get("src") or ""
        if not (re.search(r"\.(jpe?g|png|webp)", src, re.I) or "/image" in src or "/media/" in src):
            continue
        if JUNK_IMG.search(src):
            continue
        w = img.get("width")
        if w and str(w).isdigit() and int(w) < 200:
            continue
        urls.append(urljoin(base, re.sub(r"-\d+x\d+(?=\.\w+$)", "", src)))
    return list(dict.fromkeys(urls))[:10]


def extract_from_html(
    html: str,
    url: str,
    *,
    source: str = "link",
    label: str = "Enlace manual",
    name_selector: str | None = None,
) -> Dog:
    s = BeautifulSoup(html, "lxml")
    host = urlparse(url).netloc.replace("www.", "")

    ld = _jsonld(s)
    # el <h1> manda: muchos gestores dejan un <title> genérico ("Animal Detail Page")
    candidates: list[str] = []
    if name_selector:
        candidates.append(_txt(s.select_one(name_selector)))
    candidates += [
        _txt(s.select_one("h1")),
        ld.get("name") if isinstance(ld.get("name"), str) else "",
        (s.select_one('meta[property="og:title"]') or {}).get("content", ""),
        s.title.get_text(strip=True) if s.title else "",
    ]
    name = ""
    for cand in candidates:
        if not cand:
            continue
        head = N.clean_name(re.split(r"[|–—]| - ", str(cand))[0])
        if head and not GENERIC_TITLE.fullmatch(N.key(head)):
            name = head
            break

    pairs = _labeled_pairs(s)
    text = _main_text(s)
    inline = _inline_fields(text)

    def pick(slot: str) -> str:
        for k, v in pairs.items():
            if re.fullmatch(LABELS[slot], k, re.I) or re.match(LABELS[slot], k, re.I):
                return v
        return inline.get(slot, "")

    desc = (
        N.clean_text(ld.get("description") or "")
        or (s.select_one('meta[property="og:description"]') or {}).get("content", "")
    )
    if len(text) > len(desc):
        desc = text

    birth = N.parse_birth_date(pick("birth"))
    age = N.months_since(birth) or N.parse_age_months(pick("age")) or N.parse_age_months(desc)
    breed, breed_type = N.norm_breed(pick("breed"), desc)
    location = pick("location")
    province = N.norm_province(location, f"{desc[:800]} {host}")
    sex = N.norm_sex(pick("sex"))
    size = N.norm_size(pick("size"))
    weight = N.parse_weight(pick("weight"))

    shelter = pick("shelter") or host

    return Dog(
        id=make_id(source, f"{host}-{N.slugify(name) or urlparse(url).path}"),
        source=source,
        source_label=label,
        url=url,
        entry="link" if source == "link" else "scraper",
        name=name or "Sin nombre",
        sex=sex,
        birth_date=birth,
        age_months=age,
        size=size,
        weight_kg=weight,
        breed=breed,
        breed_type=breed_type,
        location=location,
        province=province,
        shelter=shelter[:60],
        shelter_url=f"https://{host}",
        photos=_images(s, url),
        description=desc,
        status=N.norm_status(desc[:300]),
    ).finalize()


def extract_from_url(url: str, *, use_browser: bool = False, source: str = "link", label: str = "Enlace manual") -> Dog:
    html = ""
    if use_browser:
        from .browser import render

        html = render(url) or ""
    if not html:
        r = get(url)
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        html = r.text
    dog = extract_from_html(html, url, source=source, label=label)
    # si la página es JS y salió vacía, reintentar con navegador
    if not use_browser and (not dog.description or len(dog.description) < 60) and not dog.sex:
        try:
            from .browser import render

            rendered = render(url)
            if rendered and len(rendered) > len(html):
                dog = extract_from_html(rendered, url, source=source, label=label)
        except Exception:
            pass
    return dog
