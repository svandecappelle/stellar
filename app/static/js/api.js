/* ============================================================
   api.js — couche d'accès à l'API Flask.
   Même origine que le serveur : l'authentification repose sur
   le cookie de session Flask-Login, donc `credentials: same-origin`.
   ============================================================ */

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new ApiError('Serveur injoignable', 0);
  }

  if (res.status === 204) return null;

  const raw = await res.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (e) {
      payload = raw;
    }
  }

  if (!res.ok) {
    let message;
    if (payload && typeof payload === 'object' && payload.message) {
      message = payload.message;
    } else if (typeof payload === 'string' && payload) {
      // abort(401, "...") renvoie du HTML : on en extrait le texte utile.
      message = payload.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    }
    throw new ApiError(message || `Erreur ${res.status}`, res.status);
  }

  return payload;
}

export const api = {
  /* ---- authentification ---- */
  me: () => request('/api/auth/me'),
  login: (username, password, remember = true) =>
    request('/api/auth/login', {
      method: 'POST',
      body: { username, password, remember_me: remember },
    }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  /* ---- catalogue statique (coûts des vaisseaux / défenses) ---- */
  catalog: () => request('/api/catalog'),

  /* ---- galaxies ---- */
  galaxies: () => request('/api/galaxies'),

  /* ---- territoires ---- */
  /* Un territoire appartient a un systeme, qui appartient a une galaxie : on
     lit donc la liste par galaxie. Sans galaxie choisie, on retombe sur la
     liste tous horizons, seule reponse a "ou ai-je quelque chose ?". */
  myTerritories: (galaxy) =>
    request(
      galaxy
        ? `/api/galaxy/${encodeURIComponent(galaxy)}/territories`
        : '/api/territories'
    ).then((r) => (r && r.territories) || []),
  /* /update recalcule les ressources côté serveur avant de sérialiser :
     c'est le seul appel qui garantit un état à jour. */
  territory: (id) => request(`/api/territory/${id}/update`, { method: 'POST' }),
  territoryEvents: (id) => request(`/api/territory/${id}/events`),
  territoryShips: (id) => request(`/api/territory/${id}/ships`),
  territoryDefenses: (id) => request(`/api/territory/${id}/defenses`),

  /* ---- systèmes ---- */
  systemTerritories: (id) =>
    request(`/api/system/${id}/territories`).then((r) => (r && r.territories) || []),

  /* ---- constructions ---- */
  upgradeBuilding: (territoryId, building) =>
    request(`/api/territory/${territoryId}/${building}`, { method: 'POST' }),
  buildShips: (territoryId, type, quantity) =>
    request(`/api/territory/${territoryId}/ship`, {
      method: 'POST',
      body: { items: [{ type, quantity }] },
    }),
  buildDefenses: (territoryId, type, quantity) =>
    request(`/api/territory/${territoryId}/defense`, {
      method: 'POST',
      body: { items: [{ type, quantity }] },
    }),
};
