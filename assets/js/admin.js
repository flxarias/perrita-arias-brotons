/* =============================================================================
   Panel de alta: extracción desde enlace + formulario manual + guardado.
   ========================================================================== */

(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const PROVINCES = ['Alicante','Valencia','Murcia','Albacete','Castellón','Almería','Madrid','Barcelona',
    'Tarragona','Zaragoza','Teruel','Cuenca','Ciudad Real','Toledo','Guadalajara','Jaén','Granada','Baleares',
    'Girona','Lleida','Huesca','Soria','Segovia','Cádiz','Sevilla','Málaga','Córdoba','Badajoz','Cáceres',
    'Asturias','Cantabria','Navarra','La Rioja','Burgos','León','Salamanca','Valladolid','Zamora','Palencia',
    'Ávila','Huelva','Lugo','Ourense','Pontevedra','A Coruña','Bizkaia','Gipuzkoa','Álava','Las Palmas',
    'Santa Cruz de Tenerife','Ceuta','Melilla'];

  const TIERS = {
    core: ['Alicante'],
    near: ['Murcia', 'Valencia', 'Albacete', 'Castellón', 'Almería'],
    east: ['Madrid','Barcelona','Tarragona','Zaragoza','Teruel','Cuenca','Ciudad Real','Toledo',
           'Guadalajara','Jaén','Granada','Baleares','Girona','Lleida','Huesca','Soria','Segovia','Cádiz'],
  };
  const TIER_SCORE = { core: 1, near: .72, east: .42, far: .1, desconocido: .3 };
  const WEIGHTS = { sex: 26, age: 26, size: 18, geo: 18, breed: 6, kids: 6 };

  const PPP = /pit ?bull|staffordshire|amstaff|rottweiler|dogo argentino|fila brasileiro|tosa inu|akita|doberman|presa canario|dogo canario|ca de bou|bullmastiff|mastin napolitano|american bully/i;

  let current = null;   // ficha en edición

  /* ------------------------------------------------------------ utilidades */

  const fold = (s) => (s || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  const stripNoise = (s) => (s || '').replace(/https?:\/\/\S+|www\.\S+|\S+@\S+\.\S+|\b\d{6,}\b/g, ' ');

  function parseSex(t) {
    const k = fold(t);
    if (/\bhembra\b|\bfemale\b|\bperrita\b|\bfemella\b/.test(k)) return 'hembra';
    if (/\bmacho\b|\bmale\b|\bmascle\b/.test(k)) return 'macho';
    return '';
  }

  function parseSize(t) {
    const k = fold(t);
    if (/\bmini\b|\btoy\b/.test(k)) return 'mini';
    if (/pequen|\bsmall\b/.test(k)) return 'pequeno';
    if (/median|\bmedium\b/.test(k)) return 'mediano';
    if (/gigante|\bgiant\b/.test(k)) return 'gigante';
    if (/grande|\blarge\b/.test(k)) return 'grande';
    return '';
  }

  const sizeFromWeight = (kg) => !kg ? '' : kg < 5 ? 'mini' : kg < 12 ? 'pequeno' : kg < 25 ? 'mediano' : kg < 45 ? 'grande' : 'gigante';

  function parseAgeMonths(t) {
    const k = fold(stripNoise(t));
    let m;
    if ((m = k.match(/\b(\d{1,2})\s*(?:anos|anys|years?)\D{0,12}?(\d{1,2})\s*(?:meses|months?)/))) return +m[1] * 12 + +m[2];
    if ((m = k.match(/\b(\d{1,2})\s*(?:anos|anys|years?)\b/))) return +m[1] * 12;
    if ((m = k.match(/\b(\d{1,3})\s*(?:meses|months?)\b/))) return +m[1];
    if ((m = k.match(/\b(\d{1,3})\s*(?:semanas|weeks?)\b/))) return Math.floor(+m[1] / 4);
    if (/\bano y medio\b/.test(k)) return 18;
    if (/\bun ano\b/.test(k)) return 12;
    if (/recien nacid|\bbebe\b|\blactante\b/.test(k)) return 1;
    if (/\bcachorr/.test(k)) return 6;
    return null;
  }

  function parseBirth(t) {
    let m = (t || '').match(/(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
    if (m) return `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`;
    m = (t || '').match(/(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})/);
    if (m) {
      let y = +m[3]; if (y < 100) y += 2000;
      if (y < 1995 || y > new Date().getFullYear() + 1) return '';
      return `${y}-${String(m[2]).padStart(2, '0')}-${String(m[1]).padStart(2, '0')}`;
    }
    return '';
  }

  function parseProvince(t) {
    const k = fold(t);
    const CITY = { elche: 'Alicante', elx: 'Alicante', torrevieja: 'Alicante', orihuela: 'Alicante',
      benidorm: 'Alicante', alcoy: 'Alicante', elda: 'Alicante', denia: 'Alicante', villena: 'Alicante',
      ibi: 'Alicante', novelda: 'Alicante', crevillente: 'Alicante', 'callosa de segura': 'Alicante',
      cartagena: 'Murcia', lorca: 'Murcia', gandia: 'Valencia', torrent: 'Valencia' };
    for (const p of PROVINCES) if (new RegExp(`\\b${fold(p)}\\b`).test(k)) return p;
    for (const [c, p] of Object.entries(CITY)) if (new RegExp(`\\b${c}\\b`).test(k)) return p;
    return '';
  }

  const tierOf = (p) => !p ? 'desconocido'
    : TIERS.core.includes(p) ? 'core' : TIERS.near.includes(p) ? 'near' : TIERS.east.includes(p) ? 'east' : 'far';

  function field(text, labelRe) {
    const m = text.match(new RegExp(`(?:${labelRe})\\s*[:\\-–]?\\s*\\n?\\s*([^\\n|•·,;]{1,60})`, 'i'));
    return m ? m[1].trim() : '';
  }

  /* --------------------------------------------------------- extracción web */

  /**
   * El navegador no puede leer otro dominio por CORS, así que se pasa por un
   * lector público que devuelve el texto de la página con cabeceras abiertas.
   * Solo se le envía la URL pública del anuncio.
   */
  async function readRemote(url) {
    const attempts = [
      { url, direct: true },
      { url: 'https://r.jina.ai/' + url, direct: false },
    ];
    for (const a of attempts) {
      try {
        const res = await fetch(a.url, { headers: a.direct ? {} : { Accept: 'text/plain' } });
        if (!res.ok) continue;
        const body = await res.text();
        if (body && body.length > 200) return { body, direct: a.direct };
      } catch { /* siguiente intento */ }
    }
    throw new Error('No se ha podido leer la página. Rellena la ficha a mano con lo que veas en el anuncio.');
  }

  function extractFrom(text, url) {
    const isHTML = /<\/?[a-z][\s\S]*>/i.test(text.slice(0, 800));
    let plain = text, title = '', images = [];

    if (isHTML) {
      const doc = new DOMParser().parseFromString(text, 'text/html');
      doc.querySelectorAll('script,style,nav,footer,header,noscript').forEach((n) => n.remove());
      title = doc.querySelector('h1')?.textContent?.trim()
        || doc.querySelector('meta[property="og:title"]')?.content
        || doc.title || '';
      images = [...doc.querySelectorAll('img[src]')]
        .map((i) => new URL(i.getAttribute('src'), url).href)
        .filter((s) => /\.(jpe?g|png|webp)/i.test(s) && !/logo|icon|avatar|sprite|placeholder/i.test(s));
      const og = doc.querySelector('meta[property="og:image"]')?.content;
      if (og) images.unshift(new URL(og, url).href);
      plain = (doc.querySelector('main,article,.entry-content') || doc.body).innerText || doc.body.textContent || '';
    } else {
      // salida del lector: markdown con "Title:" y enlaces de imagen
      title = (text.match(/^Title:\s*(.+)$/m) || [])[1] || '';
      images = [...text.matchAll(/!\[[^\]]*\]\((https?:\/\/[^)\s]+)\)/g)].map((m) => m[1]);
      plain = text;
    }

    const name = (title.split(/[|–—]| - /)[0] || '')
      .replace(/^(adopta a|adoptar a|conoce a|ficha de)\s+/i, '')
      .replace(/\b(animal|pet|dog|detail|page|ficha|en adopci[óo]n)\b/gi, '')
      .trim().slice(0, 40);

    const birth = parseBirth(field(plain, 'nacimiento|f\\.? ?nac'));
    const weight = parseFloat((field(plain, 'peso') || '').replace(',', '.')) || null;
    const sex = parseSex(field(plain, 'sexo|g[ée]nero') || plain.slice(0, 1200));
    const size = parseSize(field(plain, 'tama[ñn]o|talla|porte')) || sizeFromWeight(weight);
    const age = birth ? monthsSince(birth)
      : parseAgeMonths(field(plain, 'edad')) ?? parseAgeMonths(plain.slice(0, 2500));
    const breed = field(plain, 'raza') || '';
    const place = field(plain, 'zona|ubicaci[óo]n|localidad|provincia|municipio') || '';

    return {
      name: name || 'Sin nombre',
      sex,
      birth_date: birth,
      age_months: age ?? '',
      size,
      weight_kg: weight ?? '',
      breed,
      breed_type: /mestiz/i.test(breed) ? 'mestizo' : /mezcla|cruce/i.test(breed) ? 'mezcla' : breed ? 'raza' : 'desconocido',
      province: parseProvince(place) || parseProvince(plain.slice(0, 2500)) || parseProvince(url),
      location: place,
      shelter: new URL(url).hostname.replace(/^www\./, ''),
      url,
      photos: [...new Set(images)].slice(0, 8).join('\n'),
      description: plain.replace(/\n{3,}/g, '\n\n').trim().slice(0, 3000),
      status: 'disponible',
      good_with_kids: /buen[oa] con ni[ñn]|apto para ni[ñn]/i.test(plain),
      sterilized: /esteriliz|castrad/i.test(plain),
      vaccinated: /vacunad/i.test(plain),
      chipped: /microchip|con chip/i.test(plain),
    };
  }

  function monthsSince(iso) {
    const d = new Date(iso), n = new Date();
    return Math.max(0, (n.getFullYear() - d.getFullYear()) * 12 + (n.getMonth() - d.getMonth()));
  }

  /* ------------------------------------------------------------- afinidad */

  function score(f) {
    const R = {};
    const age = f.age_months === '' || f.age_months == null ? null : +f.age_months;

    R.sexo = f.sex === 'hembra' ? [1, 'hembra'] : !f.sex ? [.25, 'sexo sin confirmar'] : [0, 'macho'];
    R.edad = age == null ? [.35, 'edad sin confirmar']
      : age <= 6 ? [1, `${age} meses — cachorra`]
      : age <= 18 ? [1 - .4 * (age - 6) / 12, `${age} meses — muy joven`]
      : age <= 36 ? [.35, 'joven'] : age <= 84 ? [.12, 'adulta'] : [.04, 'senior'];
    const pref = ['mini', 'pequeno', 'mediano'];
    R['tamaño'] = !f.size ? [.35, 'tamaño sin confirmar']
      : pref.includes(f.size) ? [1, f.size]
      : f.size === 'grande' ? [.25, 'grande'] : [.05, 'gigante'];
    const tier = tierOf(f.province);
    R.zona = [TIER_SCORE[tier], f.province || 'zona sin confirmar'];
    R.raza = { raza: [1, 'de raza'], mezcla: [.85, 'mezcla'], mestizo: [.55, 'mestiza'], desconocido: [.4, 'sin confirmar'] }[f.breed_type || 'desconocido'];
    R['niñas'] = f.good_with_kids ? [1, 'buena con niños'] : [.5, 'sin confirmar'];

    const keys = { sexo: 'sex', edad: 'age', 'tamaño': 'size', zona: 'geo', raza: 'breed', 'niñas': 'kids' };
    const total = Object.values(WEIGHTS).reduce((a, b) => a + b, 0);
    let s = Object.entries(R).reduce((acc, [k, [v]]) => acc + v * WEIGHTS[keys[k]], 0) / total * 100;
    if (PPP.test(f.breed || '')) s *= .25;
    if (f.status === 'adoptado') s *= .15;
    if (f.status === 'reservado') s *= .6;
    return { score: Math.round(Math.max(0, Math.min(100, s))), breakdown: R };
  }

  function renderScore(f) {
    const { score: s, breakdown } = score(f);
    const c = s >= 75 ? 'var(--green)' : s >= 55 ? 'var(--gold)' : 'var(--line-2)';
    $('#scorePreview').innerHTML = `
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <div class="ring d-ring" style="--p:${s};--ring-c:${c}"><span>${s}</span></div>
        <p style="margin:0;color:var(--muted);font-size:.86rem">Sobre 100, según los criterios de <code>config/criteria.json</code>.</p>
      </div>
      <div class="why">${Object.entries(breakdown).map(([k, [v, t]]) => `
        <div class="why__row">
          <span class="why__label">${k}</span>
          <span class="why__bar"><i style="width:${Math.round(v * 100)}%"></i></span>
          <span class="why__val">${t}</span>
        </div>`).join('')}</div>`;
  }

  /* ------------------------------------------------------------ formulario */

  function fillForm(data) {
    const form = $('#form');
    Object.entries(data).forEach(([k, v]) => {
      const el = form.elements[k];
      if (!el) return;
      if (el.type === 'checkbox') el.checked = Boolean(v);
      else el.value = v ?? '';
    });
    current = data;
    $('#editor').hidden = false;
    syncPreview();
    $('#editor').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function readForm() {
    const fd = new FormData($('#form'));
    const o = Object.fromEntries(fd.entries());
    ['good_with_kids', 'sterilized', 'vaccinated', 'chipped'].forEach((k) => { o[k] = $('#form').elements[k].checked; });
    return o;
  }

  function toRecord(f) {
    const { score: s, breakdown } = score(f);
    const slug = fold(f.name).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'ficha';
    const stamp = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    const photos = (f.photos || '').split('\n').map((s2) => s2.trim()).filter(Boolean);
    const age = f.age_months === '' ? null : +f.age_months;
    const band = age == null ? null : age < 12 ? 'cachorro' : age < 36 ? 'joven' : age < 96 ? 'adulto' : 'senior';

    return {
      id: (current?.id) || `manual:${slug}-${Date.now().toString(36)}`,
      source: 'manual',
      source_label: 'Alta manual',
      url: f.url || '',
      entry: 'manual',
      name: f.name,
      sex: f.sex || null,
      sex_inferred: false,
      birth_date: f.birth_date || null,
      age_months: age,
      age_estimated: Boolean(age != null && !f.birth_date),
      age_band: band,
      size: f.size || null,
      size_inferred: false,
      weight_kg: f.weight_kg === '' ? null : +f.weight_kg,
      breed: f.breed || null,
      breed_type: f.breed_type || 'desconocido',
      ppp: PPP.test(f.breed || ''),
      province: f.province || null,
      location: f.location || '',
      shelter: f.shelter || '',
      shelter_url: '',
      shelter_kind: '',
      contact: '',
      photo: photos[0] || '',
      photos,
      description: f.description || '',
      traits: f.good_with_kids ? { good_with_kids: true } : {},
      health: Object.fromEntries(['sterilized', 'vaccinated', 'chipped'].filter((k) => f[k]).map((k) => [k, true])),
      status: f.status || 'disponible',
      urgent: f.status === 'urgente',
      first_seen: current?.first_seen || stamp,
      last_seen: stamp,
      updated_at: stamp,
      gone_since: null,
      content_hash: '',
      score: s,
      score_breakdown: Object.fromEntries(Object.entries(breakdown).map(([k, [v, t]]) => [k, { value: +v.toFixed(2), weight: 0, text: t }])),
      flags: [],
    };
  }

  function syncPreview() {
    const f = readForm();
    renderScore(f);
    $('#jsonPreview').textContent = JSON.stringify(toRecord(f), null, 1);
  }

  /* --------------------------------------------------------------- guardado */

  function guardar() {
    const rec = toRecord(readForm());
    if (!rec.name || rec.name === 'Sin nombre') {
      return status('#saveStatus', 'Ponle un nombre antes de guardar.', 'err');
    }
    const total = PAB.saveOwn(rec);
    current = rec;
    status('#saveStatus',
      `Guardada. Ya está en el <a href="index.html#${encodeURIComponent(rec.id)}">buscador</a>, ` +
      `en la <a href="datos.html">base de datos</a> y en el CSV descargable. ` +
      `Llevas ${total} ficha${total === 1 ? '' : 's'} propia${total === 1 ? '' : 's'}.`, 'ok');
    toast('Ficha guardada');
    pintarPropias();
  }

  /** Lista de lo ya guardado, para poder revisarlo o quitarlo. */
  function pintarPropias() {
    const caja = $('#propias');
    if (!caja) return;
    const arr = PAB.ownDogs();
    if (!arr.length) { caja.hidden = true; return; }
    caja.hidden = false;
    caja.innerHTML = `<h2>Tus fichas <span class="pill-n">${arr.length}</span></h2>
      <p class="hint">Guardadas en este navegador. Ya cuentan en el buscador, en la base de datos y en el CSV.</p>
      <div class="panel">
        <ul class="propias">${arr.map((d) => `
          <li>
            <span class="propias__foto">${d.photo
              ? `<img src="${d.photo.replace(/"/g, '&quot;')}" alt="" loading="lazy" referrerpolicy="no-referrer">`
              : '<span class="noimg">🐕</span>'}</span>
            <span class="propias__txt"><strong>${d.name}</strong><small>${PAB.ageText(d)} · ${PAB.sizeText(d)} · ${d.province || 'sin zona'}</small></span>
            <span class="propias__score">${d.score}</span>
            <button class="propias__x" data-id="${d.id}" aria-label="Quitar ${d.name}">×</button>
          </li>`).join('')}</ul>
        <div class="row2" style="margin-top:14px">
          <button class="btn btn--block" id="expJson">Exportar JSON</button>
          <button class="btn btn--block" id="expCsv">Exportar CSV</button>
        </div>
      </div>`;

    $$('.propias__x').forEach((b) => b.addEventListener('click', () => {
      PAB.removeOwn(b.dataset.id);
      pintarPropias();
      toast('Ficha eliminada');
    }));
    $('#expJson').addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(PAB.ownDogs(), null, 1)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'fichas-propias.json'; a.click();
      URL.revokeObjectURL(a.href);
    });
    $('#expCsv').addEventListener('click', () => CSV.download(
      PAB.ownDogs().map((d) => ({ ...d, _tier: PAB.tierOf(d.province) })), 'fichas-propias.csv'));
  }

  function download() {
    const rec = toRecord(readForm());
    const blob = new Blob([JSON.stringify(rec, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${rec.id.replace(/[:]/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast('JSON descargado');
  }

  /* -------------------------------------------------------------------- UI */

  function status(sel, html, cls = '') {
    const el = $(sel);
    el.className = 'status ' + cls;
    el.innerHTML = html;
  }

  let toastT;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg; el.classList.add('is-on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('is-on'), 2200);
  }

  function showTab(which) {
    const map = { Link: 'paneLink', Manual: 'paneManual' };
    Object.entries(map).forEach(([k, pane]) => {
      $('#tab' + k).setAttribute('aria-selected', k === which);
      $('#' + pane).hidden = k !== which;
    });
    if (which === 'Manual') {
      current = null;
      $('#form').reset();
      $('#editor').hidden = false;
      syncPreview();
    }
  }

  /* ------------------------------------------------------------------ init */

  function init() {
    $('#provinces').innerHTML = PROVINCES.map((p) => `<option value="${p}">`).join('');
    $('#paneManual').innerHTML = '<p class="hint" style="margin:0">Rellena la ficha de abajo. Solo el nombre es obligatorio.</p>';

    ['Link', 'Manual'].forEach((k) => $('#tab' + k).addEventListener('click', () => showTab(k)));

    $('#form').addEventListener('input', syncPreview);
    $('#form').addEventListener('change', syncPreview);
    $('#guardar').addEventListener('click', guardar);
    $('#saveDownload').addEventListener('click', download);

    $('#extract').addEventListener('click', async () => {
      const url = $('#url').value.trim();
      if (!url) return status('#extractStatus', 'Pega primero un enlace.', 'err');
      status('#extractStatus', '<span class="spin"></span> Leyendo la página…');
      try {
        const { body, direct } = await readRemote(url);
        fillForm(extractFrom(body, url));
        status('#extractStatus', `Datos extraídos${direct ? '' : ' (vía lector público)'}. Revísalos abajo.`, 'ok');
      } catch (e) {
        status('#extractStatus', e.message, 'err');
      }
    });

    pintarPropias();

    // ?url=… permite compartir un anuncio directamente al panel
    const pre = new URLSearchParams(location.search).get('url');
    if (pre) { $('#url').value = pre; $('#extract').click(); }
  }

  init();
})();
