"""Normalización de los campos heterogéneos que devuelve cada protectora.

Todas las fuentes escriben lo mismo de formas distintas ("Hembra", "♀", "female",
"perrita"). Aquí se traduce todo a un vocabulario único que luego consume el
scoring y la web.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

# --------------------------------------------------------------------------- texto


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def slugify(s: str) -> str:
    s = strip_accents(s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def key(s: str) -> str:
    """Clave de comparación: sin acentos, minúsculas, sin puntuación."""
    return re.sub(r"[^a-z0-9 ]+", " ", strip_accents(s or "").lower()).strip()


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def clean_name(s: str | None) -> str:
    s = clean_text(s)
    s = re.sub(r"^(adopta a|adoptar a|conoce a|ficha de)\s+", "", s, flags=re.I)
    s = re.sub(r"\s*\((adoptad[oa]|reservad[oa])\)\s*$", "", s, flags=re.I)
    s = s.strip(" -–—·|")
    # las protectoras escriben el nombre en mayúsculas o en minúsculas sin criterio
    if len(s) > 2 and (s.isupper() or s.islower()):
        s = s.title()
    return s[:60]


# --------------------------------------------------------------------------- sexo

SEX_FEMALE = {"hembra", "female", "h", "f", "perrita", "chica", "femenino", "femella", "♀"}
SEX_MALE = {"macho", "male", "m", "perro", "chico", "masculino", "mascle", "♂"}


def norm_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    k = key(str(raw))
    if k in SEX_FEMALE or re.search(r"\bhembra\b|\bfemale\b|\bperrita\b|\bfemella\b", k):
        return "hembra"
    if k in SEX_MALE or re.search(r"\bmacho\b|\bmale\b|\bmascle\b", k):
        return "macho"
    return None


def guess_sex_from_text(text: str) -> str | None:
    """Último recurso: deducir el sexo por la redacción de la ficha."""
    t = key(text)
    fem = len(re.findall(r"\b(ella|perrita|una perra|la perra|es muy buena|cariñosa|carinosa|juguetona|tranquila|preciosa|adoptada|esterilizada|castrada)\b", t))
    mas = len(re.findall(r"\b(el|perrito|un perro|el perro|es muy bueno|cariñoso|carinoso|juguetón|jugueton|tranquilo|precioso|adoptado|esterilizado|castrado)\b", t))
    if fem >= mas + 2:
        return "hembra"
    if mas >= fem + 2:
        return "macho"
    return None


# --------------------------------------------------------------------------- tamaño

SIZE_ORDER = ["mini", "pequeno", "mediano", "grande", "gigante"]
SIZE_LABEL = {
    "mini": "Mini",
    "pequeno": "Pequeño",
    "mediano": "Mediano",
    "grande": "Grande",
    "gigante": "Gigante",
}


def norm_size(raw: str | None) -> str | None:
    if not raw:
        return None
    k = key(str(raw))
    if re.search(r"\bmini\b|toy|muy pequen", k):
        return "mini"
    if re.search(r"pequen|small|petit|\bs\b", k):
        return "pequeno"
    if re.search(r"median|medium|mitjan|\bm\b", k):
        return "mediano"
    if re.search(r"gigante|giant|xl", k):
        return "gigante"
    if re.search(r"grande|large|gran\b|\bl\b", k):
        return "grande"
    return None


def size_from_weight(kg: float | None) -> str | None:
    if not kg or kg <= 0:
        return None
    if kg < 5:
        return "mini"
    if kg < 12:
        return "pequeno"
    if kg < 25:
        return "mediano"
    if kg < 45:
        return "grande"
    return "gigante"


def parse_weight(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg|kilo)", str(raw), re.I)
    if not m:
        m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", str(raw))
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return v if 0 < v < 120 else None


# --------------------------------------------------------------------------- edad

AGE_BANDS = [
    ("cachorro", 0, 12),
    ("joven", 12, 36),
    ("adulto", 36, 96),
    ("senior", 96, 10_000),
]


def age_band(months: int | None) -> str | None:
    if months is None:
        return None
    for name, lo, hi in AGE_BANDS:
        if lo <= months < hi:
            return name
    return None


def parse_birth_date(raw: str | None) -> str | None:
    """Acepta 01-06-2024, 08.09.2024, 2024-06-01, 1/6/24, junio 2024."""
    if not raw:
        return None
    s = str(raw).strip()
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            if y < 100:
                y += 2000
        else:
            m = re.search(r"([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", key(s))
            months_es = {
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
                "noviembre": 11, "diciembre": 12,
            }
            if m and m.group(1) in months_es:
                d, mo, y = 1, months_es[m.group(1)], int(m.group(2))
            else:
                return None
    try:
        dt = date(y, mo, max(1, min(d, 28)) if d > 28 else d)
    except ValueError:
        return None
    if not (1995 <= dt.year <= date.today().year + 1) or dt > date.today():
        return None
    return dt.isoformat()


def months_since(iso: str | None, ref: date | None = None) -> int | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    ref = ref or date.today()
    return max(0, (ref.year - d.year) * 12 + (ref.month - d.month))


# (patrón, conversión a meses, ¿es una estimación?)
_AGE_PATTERNS = [
    (r"\b(\d{1,2})\s*(?:anos|anys|years?)\D{0,12}?(\d{1,2})\s*(?:meses|mesos|months?)", lambda m: int(m.group(1)) * 12 + int(m.group(2)), False),
    (r"\b(\d{1,2})\s*(?:anos|anys|years?)\b", lambda m: int(m.group(1)) * 12, False),
    (r"\b(\d{1,3})\s*(?:meses|mesos|months?)\b", lambda m: int(m.group(1)), False),
    (r"\b(\d{1,3})\s*(?:semanas|weeks?)\b", lambda m: max(0, int(m.group(1)) // 4), False),
    (r"\bano\s*y\s*medio\b", lambda m: 18, False),
    (r"\bun\s*ano\b", lambda m: 12, False),
    (r"\bmes\s*y\s*medio\b", lambda m: 1, False),
    (r"\breci[e]n\s*nacid|\bbebe\b|\blactante\b|\bbiberon\b", lambda m: 1, True),
    (r"\bcachorr", lambda m: 6, True),
    (r"\bjoven\b", lambda m: 18, True),
    (r"\badult[oa]\b", lambda m: 60, True),
    (r"\bsenior\b|\banciano\b|\bmayor\b", lambda m: 108, True),
]

_URLISH = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+|\b\d{6,}\b|\b\d{3}[ .-]?\d{2}[ .-]?\d{2}[ .-]?\d{2}\b")


def parse_age_months(raw: str | None, *, with_flag: bool = False):
    """Edad en meses. `with_flag=True` devuelve (meses, es_estimación).

    Se limpian antes URLs, emails y teléfonos: son la principal fuente de
    falsos positivos (p. ej. 'lasreinasdelbiberon.org' leído como 'biberón').
    """
    if not raw:
        return (None, False) if with_flag else None
    t = key(_URLISH.sub(" ", str(raw)))
    for pat, fn, estimated in _AGE_PATTERNS:
        m = re.search(pat, t)
        if m:
            v = fn(m)
            if 0 <= v <= 300:
                return (v, estimated) if with_flag else v
    return (None, False) if with_flag else None


# --------------------------------------------------------------------------- razas

# Razas potencialmente peligrosas (RD 287/2002 + listas autonómicas habituales).
PPP_BREEDS = {
    "pit bull terrier", "pitbull", "american pitbull", "staffordshire bull terrier",
    "american staffordshire terrier", "amstaff", "staffordshire", "rottweiler",
    "dogo argentino", "fila brasileiro", "tosa inu", "akita inu", "akita americano",
    "doberman", "presa canario", "dogo canario", "presa mallorquin", "ca de bou",
    "bullmastiff", "mastin napolitano", "american bully",
}

# raza -> tamaño típico (para inferir tamaño cuando la ficha no lo dice)
BREEDS: dict[str, str] = {
    # mini / toy
    "chihuahua": "mini", "yorkshire terrier": "mini", "pomerania": "mini", "papillon": "mini",
    "bichon maltes": "mini", "maltes": "mini", "caniche toy": "mini", "pinscher miniatura": "mini",
    "shih tzu": "mini", "pekines": "mini", "bichon frise": "mini", "bichon habanero": "mini",
    "ratonero": "mini", "prague ratter": "mini",
    # pequeño
    "caniche": "pequeno", "poodle": "pequeno", "carlino": "pequeno", "pug": "pequeno",
    "jack russell": "pequeno", "west highland": "pequeno", "westy": "pequeno",
    "scottish terrier": "pequeno", "fox terrier": "pequeno", "schnauzer miniatura": "pequeno",
    "cocker spaniel": "pequeno", "cocker": "pequeno", "beagle": "pequeno",
    "teckel": "pequeno", "dachshund": "pequeno", "salchicha": "pequeno",
    "bodeguero": "pequeno", "bodeguero andaluz": "pequeno", "podenco andaluz": "pequeno",
    "cavalier king charles": "pequeno", "king charles": "pequeno", "lhasa apso": "pequeno",
    "boston terrier": "pequeno", "shiba inu": "pequeno", "corgi": "pequeno",
    "border terrier": "pequeno", "silky terrier": "pequeno", "coton de tulear": "pequeno",
    # mediano
    "border collie": "mediano", "cocker americano": "mediano", "bulldog frances": "mediano",
    "bulldog ingles": "mediano", "schnauzer": "mediano", "springer spaniel": "mediano",
    "basset hound": "mediano", "shar pei": "mediano", "chow chow": "mediano",
    "australian shepherd": "mediano", "pastor australiano": "mediano", "whippet": "mediano",
    "podenco": "mediano", "podenco ibicenco": "mediano", "podenco maneto": "mediano",
    "spaniel breton": "mediano", "breton": "mediano", "samoyedo": "mediano",
    "husky siberiano": "mediano", "husky": "mediano", "american bully": "mediano",
    "staffordshire bull terrier": "mediano", "american staffordshire terrier": "mediano",
    "pitbull": "mediano", "pit bull terrier": "mediano", "setter": "mediano",
    "galgo": "mediano", "galgo espanol": "mediano", "perro de agua": "mediano",
    "perro de agua espanol": "mediano", "mastin del pirineo": "gigante",
    # grande
    "labrador": "grande", "labrador retriever": "grande", "golden retriever": "grande",
    "pastor aleman": "grande", "pastor belga": "grande", "malinois": "grande",
    "boxer": "grande", "dalmata": "grande", "doberman": "grande", "rottweiler": "grande",
    "weimaraner": "grande", "braco": "grande", "alaskan malamute": "grande",
    "dogo argentino": "grande", "presa canario": "grande", "akita": "grande",
    "collie": "grande", "pastor belga malinois": "grande", "greyhound": "grande",
    # gigante
    "mastin": "gigante", "mastin espanol": "gigante", "san bernardo": "gigante",
    "gran danes": "gigante", "terranova": "gigante", "leonberger": "gigante",
    "bullmastiff": "gigante", "mastin napolitano": "gigante",
}

MIXED_HINTS = ("mestizo", "mestiza", "mixed", "cruce", "mezcla", "x ", " x", "mestis")


def norm_breed(raw: str | None, description: str = "") -> tuple[str | None, str]:
    """Devuelve (raza legible, tipo) donde tipo ∈ raza | mezcla | mestizo | desconocido."""
    text = clean_text(raw)
    k = key(text)
    if not k:
        # intentar rescatar la raza desde la descripción
        for b in sorted(BREEDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(b)}\b", key(description)):
                return b.title(), "mezcla"
        return None, "desconocido"

    hits = [b for b in BREEDS if re.search(rf"\b{re.escape(b)}\b", k)]
    hits.sort(key=len, reverse=True)
    mixed = any(h in k for h in MIXED_HINTS)

    if hits and mixed:
        return f"Mezcla de {hits[0].title()}", "mezcla"
    if hits:
        return hits[0].title(), "raza" if not re.search(r"\bcruce\b|\bmezcla\b", k) else "mezcla"
    if mixed:
        return "Mestizo", "mestizo"
    return text.title()[:48], "raza"


# razas y palabras que delatan que la ficha es de un gato, no de un perro
CAT_BREEDS = (
    "comun europeo", "europeo de pelo corto", "siames", "persa", "maine coon",
    "bengali", "sphynx", "british shorthair", "angora", "azul ruso", "ragdoll",
    "cartujo", "gato comun",
)


def looks_like_cat(breed: str | None = None, name: str = "", text: str = "") -> bool:
    """La mayoría de protectoras mezclan perros y gatos en el mismo listado."""
    b = key(breed or "")
    if any(c in b for c in CAT_BREEDS):
        return True
    if re.search(r"\bgat[oa]s?\b|\bmichi\b|\bfelin[oa]\b", key(name)):
        return True
    # en el texto solo valen menciones inequívocas al propio animal
    return bool(re.search(r"\b(es una gata|es un gato|esta gatita|este gatito)\b", key(text)))


def is_ppp(breed: str | None) -> bool:
    if not breed:
        return False
    k = key(breed)
    return any(re.search(rf"\b{re.escape(b)}\b", k) for b in PPP_BREEDS)


def size_from_breed(breed: str | None) -> str | None:
    if not breed:
        return None
    k = key(breed)
    for b in sorted(BREEDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(b)}\b", k):
            return BREEDS[b]
    return None


# --------------------------------------------------------------------------- geografía

PROVINCES = [
    "A Coruña", "Álava", "Albacete", "Alicante", "Almería", "Asturias", "Ávila",
    "Badajoz", "Baleares", "Barcelona", "Burgos", "Cáceres", "Cádiz", "Cantabria",
    "Castellón", "Ceuta", "Ciudad Real", "Córdoba", "Cuenca", "Girona", "Granada",
    "Guadalajara", "Gipuzkoa", "Huelva", "Huesca", "Jaén", "La Rioja", "Las Palmas",
    "León", "Lleida", "Lugo", "Madrid", "Málaga", "Melilla", "Murcia", "Navarra",
    "Ourense", "Palencia", "Pontevedra", "Salamanca", "Santa Cruz de Tenerife",
    "Segovia", "Sevilla", "Soria", "Tarragona", "Teruel", "Toledo", "Valencia",
    "Valladolid", "Bizkaia", "Zamora", "Zaragoza",
]
_PROV_BY_KEY = {key(p): p for p in PROVINCES}
_PROV_BY_KEY.update({
    "la coruna": "A Coruña", "coruna": "A Coruña", "alava": "Álava", "araba": "Álava",
    "illes balears": "Baleares", "islas baleares": "Baleares", "mallorca": "Baleares",
    "menorca": "Baleares", "ibiza": "Baleares", "eivissa": "Baleares",
    "guipuzcoa": "Gipuzkoa", "vizcaya": "Bizkaia", "gerona": "Girona", "lerida": "Lleida",
    "orense": "Ourense", "tenerife": "Santa Cruz de Tenerife",
    "castello": "Castellón", "alacant": "Alicante", "valencia valencia": "Valencia",
    "comunidad valenciana": "Valencia", "region de murcia": "Murcia",
})

# Municipios frecuentes en las fichas de la zona de búsqueda.
CITY_PROVINCE = {
    # Alicante
    "alicante": "Alicante", "elche": "Alicante", "elx": "Alicante", "torrevieja": "Alicante",
    "orihuela": "Alicante", "benidorm": "Alicante", "alcoy": "Alicante", "alcoi": "Alicante",
    "elda": "Alicante", "petrer": "Alicante", "villena": "Alicante", "denia": "Alicante",
    "javea": "Alicante", "xabia": "Alicante", "calpe": "Alicante", "calp": "Alicante",
    "altea": "Alicante", "santa pola": "Alicante", "san vicente del raspeig": "Alicante",
    "sant vicent del raspeig": "Alicante", "el campello": "Alicante", "campello": "Alicante",
    "ibi": "Alicante", "novelda": "Alicante", "aspe": "Alicante", "crevillente": "Alicante",
    "callosa de segura": "Alicante", "callosa den sarria": "Alicante", "almoradi": "Alicante",
    "guardamar": "Alicante", "pilar de la horadada": "Alicante", "rojales": "Alicante",
    "benijofar": "Alicante", "san fulgencio": "Alicante", "dolores": "Alicante",
    "monovar": "Alicante", "sax": "Alicante", "banyeres": "Alicante", "muro de alcoy": "Alicante",
    "cocentaina": "Alicante", "pego": "Alicante", "ondara": "Alicante", "teulada": "Alicante",
    "moraira": "Alicante", "la nucia": "Alicante", "villajoyosa": "Alicante",
    "la vila joiosa": "Alicante", "finestrat": "Alicante", "mutxamel": "Alicante",
    "san juan de alicante": "Alicante", "sant joan dalacant": "Alicante", "agost": "Alicante",
    "alfaz del pi": "Alicante", "lalfas del pi": "Alicante", "polop": "Alicante",
    "torellano": "Alicante", "redovan": "Alicante", "cox": "Alicante", "bigastro": "Alicante",
    "catral": "Alicante", "granja de rocamora": "Alicante", "santa pola del este": "Alicante",
    # Valencia
    "valencia": "Valencia", "gandia": "Valencia", "torrent": "Valencia", "paterna": "Valencia",
    "sagunto": "Valencia", "xativa": "Valencia", "jativa": "Valencia", "alzira": "Valencia",
    "ontinyent": "Valencia", "sueca": "Valencia", "burjassot": "Valencia", "manises": "Valencia",
    "mislata": "Valencia", "aldaia": "Valencia", "catarroja": "Valencia", "requena": "Valencia",
    "oliva": "Valencia", "cullera": "Valencia", "llíria": "Valencia", "liria": "Valencia",
    # Murcia
    "murcia": "Murcia", "cartagena": "Murcia", "lorca": "Murcia", "molina de segura": "Murcia",
    "alcantarilla": "Murcia", "yecla": "Murcia", "jumilla": "Murcia", "aguilas": "Murcia",
    "san javier": "Murcia", "torre pacheco": "Murcia", "mazarron": "Murcia", "totana": "Murcia",
    "caravaca": "Murcia", "cieza": "Murcia", "san pedro del pinatar": "Murcia",
    # Albacete / Castellón / Almería
    "albacete": "Albacete", "hellin": "Albacete", "villarrobledo": "Albacete", "almansa": "Albacete",
    "castellon": "Castellón", "vila real": "Castellón", "villarreal": "Castellón",
    "burriana": "Castellón", "vinaros": "Castellón", "benicassim": "Castellón",
    "almeria": "Almería", "roquetas de mar": "Almería", "el ejido": "Almería", "vera": "Almería",
    # Madrid y otras
    "madrid": "Madrid", "alcala de henares": "Madrid", "getafe": "Madrid", "mostoles": "Madrid",
    "leganes": "Madrid", "alcorcon": "Madrid", "fuenlabrada": "Madrid", "torrejon": "Madrid",
    "barcelona": "Barcelona", "zaragoza": "Zaragoza", "teruel": "Teruel", "cuenca": "Cuenca",
    "toledo": "Toledo", "guadalajara": "Guadalajara", "ciudad real": "Ciudad Real",
    "tarragona": "Tarragona", "reus": "Tarragona", "granada": "Granada", "jaen": "Jaén",
}


def norm_province(raw: str | None, fallback_text: str = "") -> str | None:
    for candidate in (raw, fallback_text):
        if not candidate:
            continue
        k = key(str(candidate))
        # provincia explícita
        for pk, pname in _PROV_BY_KEY.items():
            if re.search(rf"\b{re.escape(pk)}\b", k):
                return pname
        # municipio conocido
        for ck, pname in CITY_PROVINCE.items():
            if re.search(rf"\b{re.escape(ck)}\b", k):
                return pname
    return None


def geo_tier(province: str | None, criteria: dict) -> str:
    tiers = criteria["geo"]["tiers"]
    if not province:
        return "desconocido"
    if province in tiers["core"]:
        return "core"
    if province in tiers["near"]:
        return "near"
    if province in tiers["east"]:
        return "east"
    return "far"


# --------------------------------------------------------------------------- estado

STATUS_MAP = {
    "adoptado": "adoptado", "adoptada": "adoptado", "adopted": "adoptado",
    "reservado": "reservado", "reservada": "reservado", "reserved": "reservado",
    "urgente": "urgente", "urgent": "urgente",
    "acogida": "acogida", "en acogida": "acogida",
    "disponible": "disponible", "en adopcion": "disponible",
}


def norm_status(raw: str | None) -> str:
    if not raw:
        return "disponible"
    k = key(str(raw))
    for pat, val in STATUS_MAP.items():
        if pat in k:
            return val
    return "disponible"


# --------------------------------------------------------------------------- rasgos

TRAIT_PATTERNS = {
    "good_with_kids": r"bueno con nin|buena con nin|apto para nin|ideal para nin|good with kid|con nin[oa]s? si|le encantan los nin",
    "good_with_dogs": r"bueno con otros perr|buena con otros perr|sociable con perr|good with dog|se lleva bien con perr",
    "good_with_cats": r"bueno con gat|buena con gat|good with cat|compatible con gat",
    "good_at_home": r"bueno en casa|limpio en casa|tranquil[oa] en casa|good in the house",
    "playful": r"juguet|playful",
    "affectionate": r"carinos|amoros|mimos|affectionate",
    "calm": r"tranquil|calmad|equilibrad",
    "needs_experience": r"necesita experiencia|adoptante con experiencia|no apto para primerizos",
}

HEALTH_PATTERNS = {
    "vaccinated": r"vacunad|vaccinated",
    "chipped": r"microchip|con chip|chipped",
    "sterilized": r"esteriliz|castrad|sterili",
    "dewormed": r"desparasitad|dewormed",
    "passport": r"con cartilla|pasaporte|passport",
}


def extract_flags(text: str, patterns: dict[str, str]) -> dict[str, bool]:
    t = key(text)
    out: dict[str, bool] = {}
    for name, pat in patterns.items():
        if re.search(pat, t):
            neg = re.search(rf"\bno\s+(?:es\s+)?(?:\w+\s+){{0,2}}(?={pat})", t)
            out[name] = not neg
    return out


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
