/* =============================================================================
   Interfaz del buscador.
   ========================================================================== */

(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const PAGE = 24;

  const state = {
    all: [],
    view: [],
    meta: null,
    filters: PAB.loadFilters(),
    shown: PAGE,
    generatedAt: null,
  };

  /* ------------------------------------------------------------------ init */

  init();

  async function init() {
    wire();
    try {
      const { dogs, meta, generatedAt } = await PAB.load();
      state.all = dogs;
      state.meta = meta;
      state.generatedAt = generatedAt;
      hydrateSelects();
      renderHeroStats();
      renderFooter();
      restoreFilters();
      render();
      // A partir de ahora, "novedades" se cuenta desde este momento.
      setTimeout(PAB.markVisited, 4000);
      openFromHash();
    } catch (err) {
      $('#grid').innerHTML = `<p class="d-warn">No se ha podido cargar la base de datos.<br><small>${esc(err.message)}</small></p>`;
      $('#resultCount').textContent = 'Error';
    }
  }

  /* --------------------------------------------------------------- cableado */

  function wire() {
    const q = $('#q');
    let t;
    q.addEventListener('input', () => {
      $('#qClear').hidden = !q.value;
      clearTimeout(t);
      t = setTimeout(() => { state.filters.q = q.value.trim(); state.shown = PAGE; render(); }, 160);
    });
    $('#qClear').addEventListener('click', () => {
      q.value = ''; $('#qClear').hidden = true;
      state.filters.q = ''; state.shown = PAGE; render(); q.focus();
    });

    $('#sort').addEventListener('change', (e) => { state.filters.sort = e.target.value; render(); });
    $('#loadMore').addEventListener('click', () => { state.shown += PAGE; render(false); });
    $('#openFilters').addEventListener('click', () => $('#filters').showModal());
    $('#resetFilters').addEventListener('click', resetFilters);
    $('#resetFromEmpty').addEventListener('click', resetFilters);

    $$('[data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
    $$('dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) d.close(); }));

    // grupos de opciones multi-selección
    $$('.opts').forEach((group) => {
      const key = group.dataset.group;
      group.addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return;
        const v = b.dataset.v;
        const arr = state.filters[key];
        const i = arr.indexOf(v);
        i === -1 ? arr.push(v) : arr.splice(i, 1);
        b.setAttribute('aria-pressed', i === -1);
        render();
      });
    });

    $('#fProvince').addEventListener('change', (e) => { state.filters.province = e.target.value; render(); });
    $('#fShelter').addEventListener('change', (e) => { state.filters.shelter = e.target.value; render(); });

    const toggles = {
      fPhoto: 'onlyPhoto', fKids: 'onlyKids', fAvailable: 'onlyAvailable',
      fNoPPP: 'noPPP', fFav: 'onlyFav', fNew: 'onlyNew',
    };
    Object.entries(toggles).forEach(([id, key]) => {
      $('#' + id).addEventListener('change', (e) => { state.filters[key] = e.target.checked; render(); });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); }
    });
    window.addEventListener('hashchange', openFromHash);
  }

  /* ------------------------------------------------------- estado ↔ pantalla */

  function restoreFilters() {
    const f = state.filters;
    $('#q').value = f.q; $('#qClear').hidden = !f.q;
    $('#sort').value = f.sort;
    $$('.opts').forEach((g) => {
      const key = g.dataset.group;
      $$('button', g).forEach((b) => b.setAttribute('aria-pressed', f[key].includes(b.dataset.v)));
    });
    $('#fProvince').value = f.province;
    $('#fShelter').value = f.shelter;
    $('#fPhoto').checked = f.onlyPhoto;
    $('#fKids').checked = f.onlyKids;
    $('#fAvailable').checked = f.onlyAvailable;
    $('#fNoPPP').checked = f.noPPP;
    $('#fFav').checked = f.onlyFav;
    $('#fNew').checked = f.onlyNew;
  }

  function resetFilters() {
    state.filters = PAB.emptyFilters();
    state.shown = PAGE;
    restoreFilters();
    render();
    toast('Filtros restablecidos');
  }

  function hydrateSelects() {
    const provinces = [...new Set(state.all.map((d) => d.province).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
    $('#fProvince').insertAdjacentHTML('beforeend',
      provinces.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join(''));

    const shelters = [...new Set(state.all.map((d) => d.shelter || d.source_label).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'es'));
    $('#fShelter').insertAdjacentHTML('beforeend',
      shelters.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join(''));

    renderQuickChips();
  }

  const QUICK = [
    { id: 'ideal',  label: 'Encaje ideal', accent: true },
    { id: 'nuevas', label: 'Novedades' },
    { id: 'hembra', label: 'Solo hembras' },
    { id: 'cachorra', label: 'Cachorras' },
    { id: 'peqmed', label: 'Pequeña o mediana' },
    { id: 'alicante', label: 'Alicante' },
    { id: 'fav', label: '♥ Favoritas' },
  ];

  function renderQuickChips() {
    $('#quickchips').innerHTML = QUICK.map((c) =>
      `<button type="button" data-quick="${c.id}" aria-pressed="false"${c.accent ? ' class="is-accent"' : ''}>${c.label}</button>`
    ).join('');
    $('#quickchips').addEventListener('click', (e) => {
      const b = e.target.closest('[data-quick]'); if (!b) return;
      const on = b.getAttribute('aria-pressed') !== 'true';
      applyQuick(b.dataset.quick, on);
      b.setAttribute('aria-pressed', on);
      restoreFilters();
      render();
    });
  }

  function applyQuick(id, on) {
    const f = state.filters;
    const set = (key, vals) => { f[key] = on ? vals : []; };
    switch (id) {
      case 'ideal':
        if (on) { f.sex = ['hembra']; f.age = ['cachorro', 'joven']; f.size = ['mini', 'pequeno', 'mediano']; f.tier = ['core', 'near']; f.sort = 'score'; }
        else { f.sex = []; f.age = []; f.size = []; f.tier = []; }
        break;
      case 'nuevas': f.onlyNew = on; if (on) f.sort = 'new'; break;
      case 'hembra': set('sex', ['hembra']); break;
      case 'cachorra': set('age', ['cachorro']); break;
      case 'peqmed': set('size', ['mini', 'pequeno', 'mediano']); break;
      case 'alicante': set('tier', ['core']); break;
      case 'fav': f.onlyFav = on; break;
    }
    state.shown = PAGE;
  }

  function activeFilterCount() {
    const f = state.filters, d = PAB.emptyFilters();
    let n = 0;
    ['sex', 'age', 'size', 'tier', 'breedType'].forEach((k) => { if (f[k].length) n++; });
    if (f.province) n++;
    if (f.shelter) n++;
    ['onlyPhoto', 'onlyKids', 'onlyFav', 'onlyNew'].forEach((k) => { if (f[k]) n++; });
    if (f.onlyAvailable !== d.onlyAvailable) n++;
    if (f.noPPP !== d.noPPP) n++;
    return n;
  }

  /* ------------------------------------------------------------- renderizado */

  function render(resetPaging = true) {
    if (resetPaging) state.shown = PAGE;
    state.view = PAB.apply(state.all, state.filters);
    PAB.saveFilters(state.filters);

    const n = state.view.length;
    $('#resultCount').textContent = n === 0 ? 'Ninguna coincidencia'
      : n === 1 ? '1 perrita' : `${n} perritas`;
    $('#previewCount').textContent = n;

    const fc = activeFilterCount();
    $('#filterCount').hidden = fc === 0;
    $('#filterCount').textContent = fc;

    $('#grid').innerHTML = state.view.slice(0, state.shown).map(card).join('');
    $('#empty').hidden = n !== 0;
    $('#loadMore').hidden = n <= state.shown;
    syncQuickChips();

    $$('.card__img img, .d-gallery img').forEach((img) => img.addEventListener('error', onImageError));
    $$('.card__fav').forEach((b) => b.addEventListener('click', (e) => {
      e.stopPropagation();
      const on = PAB.toggleFav(b.dataset.id);
      b.setAttribute('aria-pressed', on);
      b.textContent = on ? '♥' : '♡';
      toast(on ? 'Añadida a favoritas' : 'Quitada de favoritas');
    }));
    $$('.card').forEach((c) => {
      c.addEventListener('click', () => openDetail(c.dataset.id));
      c.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(c.dataset.id); }
      });
    });
  }

  /** Marca los chips rápidos que ya están reflejados en los filtros activos. */
  function syncQuickChips() {
    const f = state.filters;
    const eq = (a, b) => a.length === b.length && b.every((v) => a.includes(v));
    const on = {
      ideal: eq(f.sex, ['hembra']) && eq(f.age, ['cachorro', 'joven'])
             && eq(f.size, ['mini', 'pequeno', 'mediano']) && eq(f.tier, ['core', 'near']),
      nuevas: f.onlyNew,
      hembra: eq(f.sex, ['hembra']),
      cachorra: eq(f.age, ['cachorro']),
      peqmed: eq(f.size, ['mini', 'pequeno', 'mediano']),
      alicante: eq(f.tier, ['core']),
      fav: f.onlyFav,
    };
    $$('[data-quick]').forEach((b) => b.setAttribute('aria-pressed', Boolean(on[b.dataset.quick])));
  }

  /** Si una foto no carga, prueba la siguiente de la ficha; si no queda ninguna,
      deja el marcador en vez de un hueco roto. */
  function onImageError(e) {
    const img = e.currentTarget;
    const alts = (img.dataset.alts || '').split('|').filter(Boolean);
    if (alts.length) {
      img.dataset.alts = alts.slice(1).join('|');
      img.src = alts[0];
      return;
    }
    const ph = document.createElement('div');
    ph.className = 'noimg';
    ph.textContent = '🐕';
    img.replaceWith(ph);
  }

  function ringStyle(score) {
    const c = score >= 75 ? 'var(--green)' : score >= 55 ? 'var(--gold)' : 'var(--line-2)';
    return `--p:${score};--ring-c:${c}`;
  }

  function card(d) {
    const fav = PAB.isFav(d.id);
    const ribbons = [];
    if (d._new) ribbons.push('<span class="ribbon ribbon--new">Nueva</span>');
    if (d.urgent) ribbons.push('<span class="ribbon ribbon--urgent">Urgente</span>');
    if (d.status === 'reservado') ribbons.push('<span class="ribbon">Reservada</span>');
    if (d.status === 'no-disponible') ribbons.push('<span class="ribbon ribbon--gone">Retirada</span>');

    const tags = [
      d.sex ? `<span class="tag tag--${d.sex === 'hembra' ? 'f' : 'm'}">${PAB.sexText(d)}</span>` : '<span class="tag tag--soft">Sexo ?</span>',
      d.age_band === 'cachorro'
        ? `<span class="tag tag--puppy">${esc(PAB.ageText(d))}</span>`
        : `<span class="tag${d.age_months == null ? ' tag--soft' : ''}">${esc(PAB.ageText(d))}</span>`,
      `<span class="tag${d.size ? '' : ' tag--soft'}">${esc(PAB.sizeText(d))}</span>`,
    ].join('');

    // las protectoras borran fotos con el tiempo: se guardan las alternativas
    // de la ficha para ir probándolas antes de rendirse
    const alts = (d.photos || []).filter((p) => p && p !== d.photo).join('|');

    // referrerpolicy="no-referrer": el servidor de alguna protectora (Villena)
    // tiene protección anti-hotlink y, al ver que la petición llega desde otro
    // dominio, devuelve un cartel de "This image was hotlinked" en vez de la
    // foto. Sin cabecera Referer sirve la imagen buena.

    return `
<article class="card" data-id="${esc(d.id)}" tabindex="0" role="button" aria-label="Ficha de ${esc(d.name)}">
  <div class="card__img">
    ${d.photo
      ? `<img src="${esc(d.photo)}" alt="${esc(d.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-alts="${esc(alts)}">`
      : '<div class="noimg">🐕</div>'}
    <div class="card__ribbons">${ribbons.join('')}</div>
    <button class="card__fav" data-id="${esc(d.id)}" aria-pressed="${fav}" aria-label="Favorita">${fav ? '♥' : '♡'}</button>
  </div>
  <div class="card__body">
    <div class="card__top">
      <h3 class="card__name">${esc(d.name)}</h3>
      <div class="ring" style="${ringStyle(d.score)}" title="Encaje ${d.score}/100"><span>${d.score}</span></div>
    </div>
    <div class="tags">${tags}</div>
    <div class="card__foot">
      <span>${esc(PAB.placeText(d))}</span><span class="dot">·</span>
      <span>${esc(d.shelter || d.source_label)}</span>
    </div>
  </div>
</article>`;
  }

  /* ------------------------------------------------------------------ ficha */

  function openFromHash() {
    const id = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    if (id && state.all.some((d) => d.id === id)) openDetail(id, false);
  }

  function openDetail(id, pushHash = true) {
    const d = state.all.find((x) => x.id === id);
    if (!d) return;
    if (pushHash) history.replaceState(null, '', '#' + encodeURIComponent(id));
    $('#detailBody').innerHTML = detailHTML(d);
    $$('.d-gallery img').forEach((img) => img.addEventListener('error', onImageError));
    const dlg = $('#detail');
    dlg.showModal();
    dlg.scrollTop = 0;
    dlg.addEventListener('close', () => history.replaceState(null, '', location.pathname), { once: true });

    $('#dFav')?.addEventListener('click', (e) => {
      const on = PAB.toggleFav(d.id);
      e.currentTarget.textContent = on ? '♥ En favoritas' : '♡ Guardar';
      render(false);
    });
    $('#dHide')?.addEventListener('click', () => {
      PAB.toggleHidden(d.id);
      dlg.close();
      render();
      renderFooter();
      toast('Ficha descartada');
    });
  }

  function detailHTML(d) {
    const photos = d.photos?.length ? d.photos : (d.photo ? [d.photo] : []);
    const gallery = photos.length
      ? photos.map((p) => `<img src="${esc(p)}" alt="${esc(d.name)}" loading="lazy" referrerpolicy="no-referrer">`).join('')
      : '<div class="noimg">🐕</div>';

    const facts = [
      ['Sexo', PAB.sexText(d)],
      ['Edad', PAB.ageText(d)],
      ['Tamaño', PAB.sizeText(d) + (d.size_inferred ? ' *' : '')],
      ['Raza', d.breed || 'Sin confirmar'],
      d.weight_kg ? ['Peso', `${d.weight_kg} kg`] : null,
      ['Zona', PAB.placeText(d)],
      ['Estado', PAB.STATUS_LABEL[d.status] || d.status],
      d.birth_date ? ['Nacimiento', new Date(d.birth_date).toLocaleDateString('es-ES')] : null,
    ].filter(Boolean);

    const why = Object.entries(d.score_breakdown || {})
      .filter(([, v]) => v && typeof v === 'object' && 'value' in v)
      .sort((a, b) => b[1].weight * b[1].value - a[1].weight * a[1].value)
      .map(([k, v]) => `
        <div class="why__row">
          <span class="why__label">${esc(k)}</span>
          <span class="why__bar"><i style="width:${Math.round(v.value * 100)}%"></i></span>
          <span class="why__val" title="${esc(v.text)}">${esc(v.text)}</span>
        </div>`).join('');

    const traits = Object.entries(d.traits || {})
      .filter(([k]) => PAB.TRAIT_LABEL[k])
      .map(([k, v]) => `<span class="pill ${v ? 'pill--ok' : 'pill--no'}">${v ? '' : 'No '}${esc(PAB.TRAIT_LABEL[k].toLowerCase())}</span>`)
      .join('');

    const health = Object.entries(d.health || {})
      .filter(([k, v]) => v && PAB.HEALTH_LABEL[k])
      .map(([k]) => `<span class="pill pill--ok">${esc(PAB.HEALTH_LABEL[k])}</span>`)
      .join('');

    const warns = [];
    if (d.ppp) warns.push('Figura como raza potencialmente peligrosa (PPP): requiere licencia y seguro, y conviene valorarlo con dos niñas en casa.');
    if (d.flags?.includes('duplicada')) warns.push('Esta ficha parece duplicada: la misma perrita está publicada en otro portal.');
    if (d.status === 'no-disponible') warns.push('Ha dejado de aparecer en la web de origen: probablemente ya esté adoptada.');
    if (d.sex_inferred) warns.push('El sexo se ha deducido del texto de la ficha, no venía como dato.');
    if (d.age_estimated) warns.push('La edad es una estimación a partir del texto de la ficha.');

    const fav = PAB.isFav(d.id);

    return `
<div class="d-hero">
  <div class="d-gallery">${gallery}</div>
  ${photos.length > 1 ? `<span class="d-count">${photos.length} fotos</span>` : ''}
</div>
<div class="d-body">
  <div class="d-top">
    <div>
      <h2 class="d-name">${esc(d.name)}</h2>
      <p class="d-sub">${esc(d.shelter || d.source_label)}${d.shelter_kind ? ' · ' + esc(d.shelter_kind) : ''} · ${esc(PAB.placeText(d))}</p>
    </div>
    <div class="ring d-ring" style="${ringStyle(d.score)}" title="Encaje ${d.score}/100"><span>${d.score}</span></div>
  </div>

  <div class="d-section">
    <h3>Datos</h3>
    <dl class="d-facts">
      ${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}
    </dl>
  </div>

  ${why ? `<div class="d-section"><h3>Por qué encaja</h3><div class="why">${why}</div></div>` : ''}
  ${traits ? `<div class="d-section"><h3>Carácter</h3><div class="pill-list">${traits}</div></div>` : ''}
  ${health ? `<div class="d-section"><h3>Se entrega</h3><div class="pill-list">${health}</div></div>` : ''}
  ${d.description ? `<div class="d-section"><h3>Su historia</h3><p class="d-text">${esc(d.description)}</p></div>` : ''}

  ${warns.map((w) => `<p class="d-warn">${esc(w)}</p>`).join('')}

  <div class="d-section">
    <h3>Trazabilidad</h3>
    <p class="d-text" style="font-size:.82rem">
      Fuente: ${esc(d.source_label)} · vista por primera vez el
      ${d.first_seen ? new Date(d.first_seen).toLocaleDateString('es-ES') : '—'}${
        d.last_seen ? `, última comprobación el ${new Date(d.last_seen).toLocaleDateString('es-ES')}` : ''}.
    </p>
  </div>

  <div class="d-actions">
    <button class="btn" id="dFav">${fav ? '♥ En favoritas' : '♡ Guardar'}</button>
    <button class="btn btn--ghost" id="dHide">Descartar</button>
    ${d.url ? `<a class="btn btn--primary" href="${esc(d.url)}" target="_blank" rel="noopener">Ver anuncio ↗</a>` : ''}
  </div>
</div>`;
  }

  /* ------------------------------------------------------------ cabecera/pie */

  function renderHeroStats() {
    const all = state.all;
    const avail = all.filter((d) => ['disponible', 'urgente', 'acogida'].includes(d.status));
    const ideal = avail.filter((d) =>
      d.sex === 'hembra' && (d.age_months ?? 999) <= 18 &&
      ['mini', 'pequeno', 'mediano'].includes(d.size) && ['core', 'near'].includes(d._tier) && !d.ppp);
    const nuevas = all.filter((d) => d._new).length;

    const stats = [
      ['En seguimiento', avail.length, false],
      ['Alto encaje', ideal.length, true],
      ['En Alicante', avail.filter((d) => d._tier === 'core').length, false],
      ['Novedades', nuevas, nuevas > 0],
    ];
    $('#heroStats').innerHTML = stats.map(([k, v, hot]) =>
      `<div><dt>${k}</dt><dd class="${hot ? 'is-accent' : ''}">${v}</dd></div>`).join('');
  }

  function renderFooter() {
    const when = state.generatedAt ? new Date(state.generatedAt) : null;
    const sources = state.meta?.source_health ? Object.keys(state.meta.source_health).length : 0;
    $('#footMeta').textContent = when
      ? `Última actualización: ${when.toLocaleString('es-ES', { dateStyle: 'long', timeStyle: 'short' })} · ${state.all.length} fichas de ${sources} fuentes`
      : `${state.all.length} fichas`;

    const link = $('#restoreHidden');
    const n = PAB.hiddenCount();
    link.hidden = n === 0;
    $('#hiddenN').textContent = n;
    link.onclick = (e) => {
      e.preventDefault();
      PAB.clearHidden();
      renderFooter();
      render();
      toast('Descartadas recuperadas');
    };
  }

  /* ----------------------------------------------------------------- toast */

  let toastT;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.add('is-on');
    clearTimeout(toastT);
    toastT = setTimeout(() => el.classList.remove('is-on'), 2200);
  }
})();
