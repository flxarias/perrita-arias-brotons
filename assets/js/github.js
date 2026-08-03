/* =============================================================================
   Puente con la API de GitHub: el repositorio *es* la base de datos.

   El token se guarda solo en el localStorage del navegador de quien lo
   introduce; nunca viaja a ningún sitio que no sea api.github.com. Debe ser un
   token de acceso personal de grano fino con permiso de Contents: read & write
   (y Actions: read & write si se quiere lanzar la extracción en servidor).
   ========================================================================== */

const GH = (() => {
  'use strict';

  const LS = { token: 'pab.gh.token', repo: 'pab.gh.repo', branch: 'pab.gh.branch' };
  const API = 'https://api.github.com';

  /** Deduce owner/repo cuando la web ya está publicada en GitHub Pages. */
  function guessRepo() {
    const saved = localStorage.getItem(LS.repo);
    if (saved) return saved;
    const m = location.hostname.match(/^([\w-]+)\.github\.io$/);
    if (m) {
      const seg = location.pathname.split('/').filter(Boolean)[0];
      return seg ? `${m[1]}/${seg}` : `${m[1]}/${m[1]}.github.io`;
    }
    return '';
  }

  const cfg = () => ({
    token: localStorage.getItem(LS.token) || '',
    repo: guessRepo(),
    branch: localStorage.getItem(LS.branch) || 'main',
  });

  function save({ token, repo, branch }) {
    if (token !== undefined) localStorage.setItem(LS.token, token.trim());
    if (repo !== undefined) localStorage.setItem(LS.repo, repo.trim());
    if (branch !== undefined) localStorage.setItem(LS.branch, (branch || 'main').trim());
  }

  const configured = () => Boolean(cfg().token && cfg().repo);

  async function req(path, opts = {}) {
    const { token } = cfg();
    const res = await fetch(API + path, {
      ...opts,
      headers: {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
        ...opts.headers,
      },
    });
    if (res.status === 204) return null;
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.message || `GitHub ${res.status}`);
    return body;
  }

  /* ------------------------------------------------------------- ficheros */

  const b64encode = (str) => btoa(String.fromCharCode(...new TextEncoder().encode(str)));
  const b64decode = (b64) => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\n/g, '')), (c) => c.charCodeAt(0)));

  async function getFile(path) {
    const { repo, branch } = cfg();
    const info = await req(`/repos/${repo}/contents/${path}?ref=${encodeURIComponent(branch)}`);
    return { sha: info.sha, text: b64decode(info.content) };
  }

  async function putFile(path, text, message, sha) {
    const { repo, branch } = cfg();
    return req(`/repos/${repo}/contents/${path}`, {
      method: 'PUT',
      body: JSON.stringify({ message, content: b64encode(text), branch, ...(sha ? { sha } : {}) }),
    });
  }

  /** Lee dogs.json, aplica `mutate` sobre el array y vuelve a commitear. */
  async function updateDogs(mutate, message) {
    const { sha, text } = await getFile('data/dogs.json');
    const db = JSON.parse(text);
    const dogs = db.dogs || db;
    const result = mutate(dogs);
    db.dogs = Array.isArray(result) ? result : dogs;
    db.count = db.dogs.length;
    db.generated_at = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    await putFile('data/dogs.json', JSON.stringify(db, null, 1) + '\n', message, sha);
    return db.dogs.length;
  }

  /* ------------------------------------------------------------- workflows */

  async function dispatch(workflow, inputs) {
    const { repo, branch } = cfg();
    await req(`/repos/${repo}/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      body: JSON.stringify({ ref: branch, inputs }),
    });
  }

  async function lastRun(workflow) {
    const { repo } = cfg();
    const r = await req(`/repos/${repo}/actions/workflows/${workflow}/runs?per_page=1`);
    return r.workflow_runs?.[0] || null;
  }

  async function whoami() {
    const u = await req('/user');
    return u.login;
  }

  return { cfg, save, configured, getFile, putFile, updateDogs, dispatch, lastRun, whoami, guessRepo };
})();
