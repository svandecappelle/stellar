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

  /* ---- reglages de galaxie ----
     Lisibles par tout joueur : ils decident des durees et des rendements qu'il
     a sous les yeux. `can_edit` dit s'il peut y toucher — moderateur de cette
     galaxie, ou administrateur. La description des parametres vient du serveur
     avec les valeurs : le formulaire se construit a partir d'elle. */
  galaxySettings: (galaxy) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/settings`),
  saveGalaxySettings: (galaxy, settings) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/settings`, {
      method: 'POST',
      body: { settings },
    }),

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
  territoryDefenses: (id) => request(`/api/territory/${id}/defenses`),

  /* ---- systèmes ---- */
  systemTerritories: (id) =>
    request(`/api/system/${id}/territories`).then((r) => (r && r.territories) || []),

  /* ---- flottes ----
     Un vaisseau assemble quitte la planete pour l'espace du systeme, ou il
     appartient a une flotte : il n'y a donc plus de vaisseaux a lire sur un
     territoire, et `/api/territory/<id>/ships` n'existe plus. Ce qui tient
     l'orbite d'une planete se reconnait au champ `orbiting_territory_id`.

     La position est en coordonnees Unity : la console ne l'affiche que pour
     situer une flotte, elle ne la pose jamais — elle n'a pas de scene. */
  systemFleets: (systemId) =>
    request(`/api/system/${systemId}/fleets`).then((r) => (r && r.fleets) || []),
  createFleet: (systemId, body = {}) =>
    request(`/api/system/${systemId}/fleet`, { method: 'POST', body }),
  renameFleet: (fleetId, name) =>
    request(`/api/fleet/${fleetId}`, { method: 'POST', body: { name } }),
  /* territoryId null detache la flotte de son orbite. */
  orbitFleet: (fleetId, territoryId) =>
    request(`/api/fleet/${fleetId}/orbit`, {
      method: 'POST',
      body: { territory_id: territoryId },
    }),
  disbandFleet: (fleetId) => request(`/api/fleet/${fleetId}`, { method: 'DELETE' }),
  transferShips: (fleetId, targetId, type, quantity) =>
    request(`/api/fleet/${fleetId}/transfer`, {
      method: 'POST',
      body: { to: targetId, items: [{ type, quantity }] },
    }),

  /* ---- constructions ---- */
  upgradeBuilding: (territoryId, building) =>
    request(`/api/territory/${territoryId}/${building}`, { method: 'POST' }),
  /* `spawn` est le point d'apparition Unity de la flotte que le serveur creera
     s'il n'en trouve aucune en orbite a la livraison. La console n'a pas de
     scene et n'en fournit donc pas : la flotte naitra a l'origine du repere,
     et Unity la reposera des que le joueur la manoeuvrera. */
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
