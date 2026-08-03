/* =============================================================================
   Capa de datos: carga, vocabulario, filtrado, orden y preferencias locales.
   Sin dependencias: se sirve tal cual desde GitHub Pages.
   ========================================================================== */

const PAB = (() => {
  'use strict';

  const DATA_URL = 'data/dogs.json';
  const META_URL = 'data/meta.json';
  const LS = {
    fav: 'pab.favoritos',
    hidden: 'pab.descartadas',
    seen: 'pab.ultimaVisita',
    filters: 'pab.filtros',
  };

  /* ---------------------------------------------------------- vocabulario */

  const SIZE_LABEL = { mini: 'Mini', pequeno: 'Pequeño', mediano: 'Mediano', grande: 'Grande', gigante: 'Gigante' };
  const SIZE_ORDER = ['mini', 'pequeno', 'mediano', 'grande', 'gigante'];
  const BAND_LABEL = { cachorro: 'Cachorra', joven: 'Joven', adulto: 'Adulta', senior: 'Senior' };
  const STATUS_LABEL = {
    disponible: 'Disponible', urgente: 'Urgente', reservado: 'Reservada',
    adoptado: 'Adoptada', acogida: 'En acogida', 'no-disponible': 'Ya no aparece',
  };
  const TRAIT_LABEL = {
    good_with_kids: 'Buena con niños', good_with_dogs: 'Buena con perros',
    good_with_cats: 'Buena con gatos', good_at_home: 'Buena en casa',
    playful: 'Juguetona', affectionate: 'Cariñosa', calm: 'Tranquila',
    needs_experience: 'Necesita experiencia',
  };
  const HEALTH_LABEL = {
    vaccinated: 'Vacunada', chipped: 'Con microchip', sterilized: 'Esterilizada',
    dewormed: 'Desparasitada', passport: 'Con cartilla',
  };
  const TIER_LABEL = { core: 'Alicante', near: 'Provincia vecina', east: 'Mitad este', far: 'Lejos', desconocido: 'Zona sin confirmar' };

  const TIERS = {
    core: ['Alicante'],
    near: ['Murcia', 'Valencia', 'Albacete', 'Castellón', 'Almería'],
    east: ['Madrid', 'Barcelona', 'Tarragona', 'Zaragoza', 'Teruel', 'Cuenca', 'Ciudad Real',
           'Toledo', 'Guadalajara', 'Jaén', 'Granada', 'Baleares', 'Girona', 'Lleida',
           'Huesca', 'Soria', 'Segovia', 'Cádiz'],
  };

  const tierOf = (p) => {
    if (!p) return 'desconocido';
    for (const t of ['core', 'near', 'east']) if (TIERS[t].includes(p)) return t;
    return 'far';
  };

  /* ------------------------------------------------------------- formatos */

  const ageText = (d) => {
    if (d.age_months == null) return 'Edad sin confirmar';
    const m = d.age_months, approx = d.age_estimated ? '~' : '';
    if (m < 1) return `${approx}Recién nacida`;
    if (m < 12) return `${approx}${m} ${m === 1 ? 'mes' : 'meses'}`;
    const y = Math.floor(m / 12), r = m % 12;
    return `${approx}${y} ${y === 1 ? 'año' : 'años'}${r ? ` y ${r} m` : ''}`;
  };

  const sizeText = (d) => SIZE_LABEL[d.size] || 'Tamaño sin confirmar';
  const sexText = (d) => (d.sex === 'hembra' ? 'Hembra' : d.sex === 'macho' ? 'Macho' : 'Sexo sin confirmar');
  const placeText = (d) => d.province || d.location || 'Zona sin confirmar';

  const fold = (s) => (s || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();

  const daysAgo = (iso) => {
    if (!iso) return Infinity;
    return (Date.now() - Date.parse(iso)) / 86400000;
  };

  /* ---------------------------------------------- preferencias del usuario */

  const readSet = (k) => new Set(JSON.parse(localStorage.getItem(k) || '[]'));
  const writeSet = (k, s) => localStorage.setItem(k, JSON.stringify([...s]));

  const favs = readSet(LS.fav);
  const hidden = readSet(LS.hidden);

  const isFav = (id) => favs.has(id);
  const toggleFav = (id) => {
    favs.has(id) ? favs.delete(id) : favs.add(id);
    writeSet(LS.fav, favs);
    return favs.has(id);
  };
  const isHidden = (id) => hidden.has(id);
  const toggleHidden = (id) => {
    hidden.has(id) ? hidden.delete(id) : hidden.add(id);
    writeSet(LS.hidden, hidden);
    return hidden.has(id);
  };
  const hiddenCount = () => hidden.size;
  const clearHidden = () => { hidden.clear(); writeSet(LS.hidden, hidden); };

  // "Novedades" = fichas vistas por primera vez después de la última visita.
  const lastVisit = Number(localStorage.getItem(LS.seen) || 0);
  const markVisited = () => localStorage.setItem(LS.seen, String(Date.now()));
  const isNew = (d) => {
    const t = Date.parse(d.first_seen || 0) || 0;
    if (!lastVisit) return daysAgo(d.first_seen) <= 3;
    return t > lastVisit;
  };

  /* ----------------------------------------------------------------- carga */

  async function load() {
    const [dogsRes, metaRes] = await Promise.all([
      fetch(DATA_URL, { cache: 'no-cache' }),
      fetch(META_URL, { cache: 'no-cache' }).catch(() => null),
    ]);
    if (!dogsRes.ok) throw new Error(`No se pudo cargar ${DATA_URL} (${dogsRes.status})`);
    const raw = await dogsRes.json();
    const dogs = (raw.dogs || raw).map((d) => ({ ...d, _tier: tierOf(d.province), _new: isNew(d) }));
    let meta = null;
    try { meta = metaRes && metaRes.ok ? await metaRes.json() : null; } catch { /* opcional */ }
    return { dogs, meta, generatedAt: raw.generated_at };
  }

  /* --------------------------------------------------------------- filtros */

  const emptyFilters = () => ({
    q: '',
    sex: [], age: [], size: [], tier: [], breedType: [],
    province: '', shelter: '',
    onlyPhoto: false, onlyKids: false, onlyAvailable: true,
    noPPP: true, onlyFav: false, onlyNew: false,
    sort: 'score',
  });

  function matches(d, f) {
    if (f.onlyAvailable && !['disponible', 'urgente', 'acogida'].includes(d.status)) return false;
    if (f.noPPP && d.ppp) return false;
    if (f.onlyPhoto && !d.photo) return false;
    if (f.onlyKids && d.traits?.good_with_kids !== true) return false;
    if (f.onlyFav && !isFav(d.id)) return false;
    if (f.onlyNew && !d._new) return false;

    if (f.sex.length) {
      const v = d.sex || '?';
      if (!f.sex.includes(v)) return false;
    }
    if (f.age.length) {
      const v = d.age_band || '?';
      if (!f.age.includes(v)) return false;
    }
    if (f.size.length) {
      const v = d.size || '?';
      if (!f.size.includes(v)) return false;
    }
    if (f.tier.length && !f.tier.includes(d._tier)) return false;
    if (f.breedType.length && !f.breedType.includes(d.breed_type)) return false;
    if (f.province && d.province !== f.province) return false;
    if (f.shelter && (d.shelter || d.source_label) !== f.shelter) return false;

    if (f.q) {
      const hay = fold([d.name, d.breed, d.shelter, d.source_label, d.province, d.location, d.description].join(' '));
      if (!f.q.split(/\s+/).filter(Boolean).every((t) => hay.includes(fold(t)))) return false;
    }
    return true;
  }

  const SORTS = {
    score: (a, b) => b.score - a.score || a.name.localeCompare(b.name, 'es'),
    new:   (a, b) => (Date.parse(b.first_seen || 0) || 0) - (Date.parse(a.first_seen || 0) || 0) || b.score - a.score,
    young: (a, b) => (a.age_months ?? 9e3) - (b.age_months ?? 9e3) || b.score - a.score,
    near:  (a, b) => ['core','near','east','far','desconocido'].indexOf(a._tier)
                   - ['core','near','east','far','desconocido'].indexOf(b._tier) || b.score - a.score,
    name:  (a, b) => a.name.localeCompare(b.name, 'es'),
  };

  function apply(dogs, f) {
    const out = dogs.filter((d) => !isHidden(d.id) && matches(d, f));
    out.sort(SORTS[f.sort] || SORTS.score);
    return out;
  }

  const saveFilters = (f) => localStorage.setItem(LS.filters, JSON.stringify(f));
  const loadFilters = () => {
    try { return { ...emptyFilters(), ...JSON.parse(localStorage.getItem(LS.filters) || '{}') }; }
    catch { return emptyFilters(); }
  };

  return {
    load, apply, matches, emptyFilters, loadFilters, saveFilters,
    isFav, toggleFav, isHidden, toggleHidden, hiddenCount, clearHidden, markVisited, isNew,
    ageText, sizeText, sexText, placeText, tierOf, daysAgo, fold,
    SIZE_LABEL, SIZE_ORDER, BAND_LABEL, STATUS_LABEL, TRAIT_LABEL, HEALTH_LABEL, TIER_LABEL,
  };
})();
