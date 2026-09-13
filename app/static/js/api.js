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

  /* Crée un compte. Il naît sans monde : le joueur réclame son premier monde
     tellurique depuis le client de jeu, et c'est cette attribution-là qui pose
     son arbre technologique. La session s'ouvre dans la foulée — redemander
     les identifiants juste après une inscription n'apporte rien. */
  register: (username, email, password) =>
    request('/api/users', {
      method: 'POST',
      body: { username, email, password },
    }),

  /* ---- appareils enregistrés ----
     Le client de jeu range une clé d'appareil pour ne plus redemander de mot
     de passe. Cette console est le seul endroit où le joueur peut la voir et
     la retirer : le jeu, lui, ne montre que la machine sur laquelle il tourne.
     Le serveur ne rend jamais la valeur d'une clé — il n'en garde que
     l'empreinte — seulement de quoi reconnaître un appareil et le fermer. */
  devices: () => request('/api/auth/tokens').then((r) => (r && r.devices) || []),
  revokeDevice: (id) => request(`/api/auth/token/${id}`, { method: 'DELETE' }),
  revokeDevices: () => request('/api/auth/tokens', { method: 'DELETE' }),

  /* ---- administration du serveur ----
     Réservé au rôle `admin`. Le moderateur n'y a pas accès : sa portée est une
     galaxie, c'est-à-dire une partie, et régler la machine ou lire ce que tous
     les joueurs ont fait en déborde. */
  schema: () => request('/api/admin/schema'),
  serverSettings: () => request('/api/admin/settings'),
  saveServerSettings: (settings) =>
    request('/api/admin/settings', { method: 'POST', body: { settings } }),
  audit: (filters = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) query.set(key, value);
    });
    const suffix = query.toString();
    return request(`/api/admin/audit${suffix ? `?${suffix}` : ''}`);
  },
  purgeAudit: (days) =>
    request('/api/admin/audit/purge', { method: 'POST', body: { days } }),
  players: () => request('/api/admin/players').then((r) => (r && r.players) || []),

  /* ---- ce qu'un visiteur voit avant d'avoir un compte ----
     Publique, et volontairement pauvre : un message d'accueil, et si les
     inscriptions sont ouvertes. Rien sur la version ni le schéma — quelqu'un
     qui cherche une faille en a plusieurs. */
  server: () => request('/api/server'),

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

  /* ---- carte de la galaxie ----
     Les systemes portent leur position, les liaisons disent lesquels sont
     voisins. Ces liaisons ne se devinent pas : la regle de voisinage vit dans
     le modele et dans le client de jeu, et une console qui la reinventerait
     dessinerait un reseau que les flottes n'empruntent pas. */
  galaxySystems: (galaxy) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/systems`).then(
      (r) => (r && r.systems) || []
    ),
  galaxyLanes: (galaxy) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/lanes`).then(
      (r) => (r && r.lanes) || []
    ),
  galaxyFleets: (galaxy) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/fleets`).then(
      (r) => (r && r.fleets) || []
    ),

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
  /* Prendre un monde : installation, colonisation, ou arrimage d'une
     plateforme orbitale. Une seule route pour les trois gestes — c'est le
     serveur qui decide lequel se joue, d'apres ce que le joueur tient deja
     dans la galaxie et d'apres l'archetype du corps.

     La console n'a donc aucune regle a recopier : elle lit le bloc `claim` du
     territoire pour savoir quoi proposer, et appelle ici. */
  claimTerritory: (id) => request(`/api/territory/${id}`, { method: 'POST' }),
  territoryDefenses: (id) => request(`/api/territory/${id}/defenses`),

  /* ---- vue d'empire ----
     Tous les mondes de la galaxie en une seule lecture, et chacun rattrape
     avant d'etre rendu — d'ou le POST, exactement comme
     `/api/territory/<id>/update` : les ressources d'un monde ne montent pas
     toutes seules en base, elles sont creditees au moment ou on le regarde.
     Une vue d'empire batie sur `myTerritories` afficherait les stocks de la
     derniere visite, et grieserait des boutons que le monde peut payer.

     Elle porte en plus ce que la liste des territoires ne porte pas : les
     defenses posees, les chantiers en cours, et ce qui tient l'orbite. */
  /* `player` n'est pose que pour regarder l'empire d'un AUTRE, ce que le
     serveur n'ouvre qu'au moderateur de la galaxie. Sans lui, c'est le sien.
     La reponse entiere est rendue et non les seuls mondes : elle porte aussi
     de qui est l'empire (`player`), si on le regarde en arbitre
     (`moderating`) et si on a le droit d'en choisir un autre
     (`can_moderate`) — trois reponses que le client ne doit pas deviner. */
  empire: (galaxy, player = null) =>
    request(
      `/api/galaxy/${encodeURIComponent(galaxy)}/empire`,
      player ? { method: 'POST', body: { player } } : { method: 'POST' }
    ),

  /* Qui tient quelque chose dans cette galaxie : la liste ou un arbitre choisit
     l'empire a ouvrir. Reservee au moderateur — `/api/admin/players` ne
     convenait pas, elle rend tous les comptes du serveur et lui est fermee. */
  galaxyPlayers: (galaxy) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/players`).then(
      (r) => (r && r.players) || []
    ),

  /* L'arbre d'un joueur, lu par un arbitre. Meme charge utile que
     `technologies` — c'est la meme fonction qui la batit cote serveur, et un
     arbitre qui lirait autre chose arbitrerait sur autre chose — plus de quoi
     savoir ce qu'on regarde. POST pour que le nom du joueur voyage dans le
     corps : il n'a pas a trainer dans les journaux d'acces d'un proxy. */
  playerResearch: (galaxy, player = null) =>
    request(
      `/api/galaxy/${encodeURIComponent(galaxy)}/research`,
      player ? { method: 'POST', body: { player } } : { method: 'POST' }
    ),

  /* Poser ou retirer des niveaux de recherche. `choice` n'a de sens que sur une
     doctrine, ou il fixe la voie. La reponse est l'arbre entier du joueur : un
     niveau change les paliers, les prerequis et les couts de toute la branche,
     et repeindre la seule ligne touchee laisserait le reste faux. */
  grantTechnology: (galaxy, player, name, amount, choice = null) =>
    request(`/api/galaxy/${encodeURIComponent(galaxy)}/research/grant`, {
      method: 'POST',
      body: choice ? { player, name, amount, choice } : { player, name, amount },
    }),

  /* Poser ou retirer un element chez un joueur, sans cout ni delai. `amount`
     est signe. La reponse est le monde entier, dans la forme de la vue
     d'empire : c'est avec elle que la console repeint la carte, et c'est la
     seule facon dont elle le peut — les routes de territoire sont fermees a
     qui n'en est pas le proprietaire. Chaque appel laisse une ligne au
     journal du serveur. */
  grant: (territoryId, kind, name, amount) =>
    request(`/api/territory/${territoryId}/grant`, {
      method: 'POST',
      body: { kind, name, amount },
    }),

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
  /* Le voyage d'une etoile a l'autre. La route est choisie par le serveur :
     c'est lui qui tient le graphe des liaisons. */
  travelFleet: (fleetId, systemId) =>
    request(`/api/fleet/${fleetId}/travel`, {
      method: 'POST',
      body: { system_id: systemId },
    }),
  stopFleetTravel: (fleetId) =>
    request(`/api/fleet/${fleetId}/travel`, { method: 'DELETE' }),
  transferShips: (fleetId, targetId, type, quantity) =>
    request(`/api/fleet/${fleetId}/transfer`, {
      method: 'POST',
      body: { to: targetId, items: [{ type, quantity }] },
    }),

  /* ---- lignes de commerce ----
     Ce qui relie les mondes d'un empire, et la seule reponse a l'isolement :
     un monde sans chemin jusqu'a la capitale perd de la stabilite a chaque
     heure, s'eteint a zero, et fait secession trois jours plus tard.

     Aucune de ces routes ne deplace de ressource. C'est le tour de jeu du
     monde de DEPART qui fait couler la ligne — une route qui transporterait a
     la demande transformerait chaque clic en convoi. */
  tradeLines: () => request('/api/trade'),
  /* Le cargo doit etre en orbite du monde d'ARRIVEE : c'est lui qui vient de
     faire le voyage, et c'est ce voyage qui etablit la route. Il est consomme
     — il devient l'infrastructure de la ligne. */
  openTradeLine: (originId, destinationId) =>
    request('/api/trade', {
      method: 'POST',
      body: { origin_id: originId, destination_id: destinationId },
    }),
  /* La declaration REMPLACE la precedente : une liste vide arrete tout sans
     fermer la ligne. */
  setTradeFlows: (lineId, flows) =>
    request(`/api/trade/${lineId}`, { method: 'POST', body: { flows } }),
  closeTradeLine: (lineId) => request(`/api/trade/${lineId}`, { method: 'DELETE' }),

  /* ---- recherche ----
     Deux lectures, et la separation compte : `technologyTree` publie la FORME
     de l'arbre — couts, durees, prerequis, effets — sans rien savoir du joueur,
     et se met en cache une fois pour toutes ; `technologies` publie l'ETAT du
     joueur dedans, et se relit a chaque geste.

     Aucun territoire nulle part : la recherche appartient au joueur, toutes
     galaxies confondues, et se paie sur l'ensemble de ses mondes. */
  technologyTree: () => request('/api/technologies/tree'),
  technologies: () => request('/api/technologies'),
  /* `choice` n'a de sens que sur une doctrine, ou il est obligatoire. */
  research: (name, choice = null) =>
    request(`/api/technology/${encodeURIComponent(name)}`, {
      method: 'POST',
      body: choice ? { choice } : {},
    }),
  cancelResearch: (eventId) =>
    request(`/api/technology/queue/${eventId}`, { method: 'DELETE' }),

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
