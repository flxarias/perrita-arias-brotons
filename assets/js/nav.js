/* =============================================================================
   Cabecera común: marca a la izquierda y menú plegado tras las tres rayitas.
   Se inyecta desde aquí para que las cuatro páginas no se desincronicen.
   ========================================================================== */

(() => {
  'use strict';

  const SECCIONES = [
    { href: 'index.html',    icono: '🔎', titulo: 'Buscador',     sub: 'Filtra y ordena por encaje' },
    { href: 'comparar.html', icono: '⚖️', titulo: 'Comparativa',  sub: 'Enfrenta candidatas cara a cara' },
    { href: 'datos.html',    icono: '📊', titulo: 'Base de datos', sub: 'Resumen y tabla completa' },
    { href: 'admin.html',    icono: '✚',  titulo: 'Añadir ficha', sub: 'Desde un enlace o a mano' },
  ];

  const actual = (location.pathname.split('/').pop() || 'index.html').toLowerCase();

  const barra = document.createElement('header');
  barra.className = 'topbar';
  barra.innerHTML = `
  <a class="topbar__brand" href="index.html">
    <span class="topbar__paw" aria-hidden="true">🐾</span>
    <span>Perrita <b>Arias Brotóns</b></span>
  </a>
  <button class="topbar__burger" id="navBurger" aria-expanded="false" aria-controls="navPanel" aria-label="Abrir el menú">
    <span></span><span></span><span></span>
  </button>
  <nav class="topbar__panel" id="navPanel" hidden>
    ${SECCIONES.map((s) => `
      <a href="${s.href}"${s.href.toLowerCase() === actual ? ' aria-current="page"' : ''}>
        <span class="topbar__icon" aria-hidden="true">${s.icono}</span>
        <span class="topbar__text"><strong>${s.titulo}</strong><small>${s.sub}</small></span>
      </a>`).join('')}
  </nav>`;

  document.body.insertAdjacentElement('afterbegin', barra);

  const burger = barra.querySelector('#navBurger');
  const panel = barra.querySelector('#navPanel');

  function abrir(si) {
    burger.setAttribute('aria-expanded', String(si));
    burger.setAttribute('aria-label', si ? 'Cerrar el menú' : 'Abrir el menú');
    panel.hidden = !si;
    barra.classList.toggle('is-open', si);
  }

  burger.addEventListener('click', () => abrir(panel.hidden));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') abrir(false); });
  document.addEventListener('click', (e) => {
    if (!barra.contains(e.target)) abrir(false);
  });
})();
