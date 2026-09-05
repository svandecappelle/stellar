/* ============================================================
   app.js — console Stellar.
   Trois vues : login, sélection de territoire, scène système.
   Aucune valeur de jeu n'est codée ici : coûts, gains et durées
   viennent tous de l'API.
   ============================================================ */

import { api, ApiError } from './api.js';
import { icon, planetGradient, roman } from './icons.js';

/* ---------- thèmes ---------- */
const THEMES = [
  { key: 'nebula', label: 'Nebula Grid' },
  { key: 'admiralty', label: 'Admiralty' },
  { key: 'drydock', label: 'Drydock' },
];
const THEME_STORAGE_KEY = 'stellar.theme';

/* ---------- ressources ----------
   `material: true` = extraite du sol, donc soumise à l'archétype de la
   planète. Les autres sont produites par un bâtiment dédié, partout. */
const RESOURCES = [
  { key: 'iron', code: 'FE', label: 'Fer', material: true },
  { key: 'carbon', code: 'CB', label: 'Carbone', material: true },
  { key: 'silicium', code: 'SI', label: 'Silicium', material: true },
  { key: 'titanium', code: 'TI', label: 'Titane', material: true },
  { key: 'cristal', code: 'CY', label: 'Cristal', material: true },
  { key: 'uranium', code: 'UR', label: 'Uranium', material: true },
  { key: 'hydrogen', code: 'HY', label: 'Hydrogène', material: true },
  { key: 'neutronium', code: 'NE', label: 'Neutronium', material: true },
  { key: 'credits', code: 'CR', label: 'Crédits' },
  { key: 'energy', code: 'EN', label: 'Énergie' },
  { key: 'food', code: 'FD', label: 'Nourriture' },
  { key: 'population', code: 'PO', label: 'Population' },
  { key: 'tritium', code: 'TR', label: 'Tritium' },
];

const RESOURCE_BY_KEY = Object.fromEntries(RESOURCES.map((r) => [r.key, r]));

/* ---------- descriptions (texte d'interface, pas de règles de jeu) ---------- */
const BUILDING_DESC = {
  power_station: "Installation de production d'énergie. Alimente l'ensemble des systèmes planétaires.",
  mater_extractor:
    "Complexe minier de surface. Ce qu'il remonte dépend entièrement du sous-sol : "
    + "une géante gazeuse ne donnera jamais de titane, quel que soit son niveau.",
  rafinery: 'Raffinerie de tritium. Transforme les volatils captés en carburant de vol.',
  economical_center: 'Centre économique. Convertit l’activité du territoire en crédits.',
  factory: 'Usine planétaire. Réduit la durée de toutes les constructions du territoire.',
  shipyard: "Complexe de construction spatiale. Débloque l'assemblage des vaisseaux et des défenses.",
  academy: 'Académie de recherche. Prérequis des programmes technologiques avancés.',
  farm: "Ferme planetaire. Seule source de nourriture, et la nourriture est ce qui fait "
    + "croitre la population : reserve vide, la croissance s'arrete et la stabilite "
    + "descend. Son rendement depend de la fertilite du monde.",
};

/* ---------- état ---------- */
const state = {
  theme: 'nebula',
  user: null,
  myTerritories: [],
  territoryId: null,
  territory: null,
  systemTerritories: [],
  events: [],
  ships: [],
  defenses: [],
  catalog: { ships: [], defenses: [] },
  tab: 'buildings',
  /* Galaxie de travail. Un territoire appartient a un systeme, qui appartient
     a une galaxie : tout ce qu'on liste en decoule. */
  galaxy: null,
  galaxies: [],
  /* Reglages de la galaxie courante et droit d'y toucher, tels que le serveur
     les rend. Relus a chaque changement de galaxie. */
  moderation: null,
};

let tickTimer = null;
let pollTimer = null;
let reloading = false;
/* Événements dont on a déjà constaté la fin : le serveur les archive au
   prochain /update, mais tant qu'ils reviennent on ne relance qu'une fois. */
let settledEvents = new Set();

/* ============================================================
   utilitaires
   ============================================================ */

const $ = (sel) => document.querySelector(sel);

/* ---------- la galaxie vit dans l'URL ----------
   ?galaxy=Milky+Way : le lien est partageable, rechargeable, et passer d'une
   galaxie a l'autre se fait aussi bien depuis la barre d'adresse que depuis
   le selecteur. */
function galaxyFromUrl() {
  try {
    return new URLSearchParams(window.location.search).get('galaxy') || null;
  } catch (e) {
    return null;
  }
}

function syncUrl() {
  try {
    const url = new URL(window.location.href);
    if (state.galaxy) url.searchParams.set('galaxy', state.galaxy);
    else url.searchParams.delete('galaxy');
    window.history.replaceState({ galaxy: state.galaxy }, '', url);
  } catch (e) {
    /* pas d'historique disponible : la vue reste juste, l'URL ne suit pas */
  }
}

function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

/* "ResourceType.mater" -> "mater", "PositionalEventType.ship" -> "ship" */
function bare(value) {
  const s = String(value || '');
  const dot = s.lastIndexOf('.');
  return dot === -1 ? s : s.slice(dot + 1);
}

/* Les dates du serveur sont des datetime.utcnow() sans fuseau :
   sans le Z, le navigateur les lirait en heure locale. */
function parseUtc(iso) {
  if (!iso) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function humanize(name) {
  return String(name || '')
    .replace(/_/g, ' ')
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtNumber(n) {
  const v = Number(n) || 0;
  const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10;
  return rounded.toLocaleString('fr-FR');
}

function fmtDelta(n) {
  const v = Number(n) || 0;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${fmtNumber(Math.abs(v))}`;
}

function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m ${String(sec).padStart(2, '0')}s`;
  return `${sec}s`;
}

/* Les coûts/gains arrivent indexés par "ResourceType.x" : on remet à plat. */
function normalizeResourceMap(map) {
  const out = {};
  Object.entries(map || {}).forEach(([k, v]) => {
    const n = Number(v) || 0;
    if (n) out[bare(k)] = n;
  });
  return out;
}

function toast(message, kind = 'info', title = null) {
  const host = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast${kind === 'err' ? ' err' : ''}`;
  el.innerHTML = `${title ? `<span class="ov">${esc(title)}</span>` : ''}${esc(message)}`;
  host.appendChild(el);
  setTimeout(() => el.remove(), kind === 'err' ? 7000 : 4000);
}

/* ============================================================
   thème
   ============================================================ */

function applyTheme(key) {
  state.theme = key;
  document.body.className = `theme-${key}`;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, key);
  } catch (e) {
    /* navigation privée : le thème reste celui de la session */
  }
  document.querySelectorAll('.theme-pick').forEach(renderThemePicker);
}

function renderThemePicker(host) {
  host.innerHTML = THEMES.map(
    (t) =>
      `<button class="tab${t.key === state.theme ? ' on' : ''}" data-theme="${t.key}" title="Direction ${esc(t.label)}">${esc(t.label)}</button>`
  ).join('');
}

function initTheme() {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_STORAGE_KEY);
  } catch (e) {
    stored = null;
  }
  applyTheme(THEMES.some((t) => t.key === stored) ? stored : 'nebula');

  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-theme]');
    if (btn) applyTheme(btn.dataset.theme);
  });
}

/* ============================================================
   galaxies
   ============================================================ */

async function loadGalaxies() {
  const known = await api.galaxies().catch(() => []);
  state.galaxies = Array.isArray(known) ? known.map((g) => g.name).filter(Boolean) : [];

  // Priorite : ce que dit l'URL, puis la galaxie deja choisie, puis la premiere.
  const wanted = galaxyFromUrl() || state.galaxy;
  state.galaxy =
    (wanted && state.galaxies.includes(wanted) && wanted) || state.galaxies[0] || wanted || null;

  fillGalaxySelect($('#login-galaxy'));
  fillGalaxySelect($('#pick-galaxy'));
  syncUrl();
}

function fillGalaxySelect(select) {
  if (!select) return;
  if (!state.galaxies.length) {
    select.innerHTML = '<option value="">Aucune galaxie</option>';
    return;
  }
  select.innerHTML = state.galaxies
    .map(
      (name) =>
        `<option value="${esc(name)}"${name === state.galaxy ? ' selected' : ''}>${esc(name)}</option>`
    )
    .join('');
}

/* Changer de galaxie relit les possessions : ce sont deux jeux de territoires
   sans rapport, et rien de la galaxie precedente ne doit rester a l'ecran. */
async function switchGalaxy(name) {
  if (!name || name === state.galaxy) return;
  state.galaxy = name;
  state.territoryId = null;
  state.territory = null;
  syncUrl();
  fillGalaxySelect($('#login-galaxy'));
  fillGalaxySelect($('#pick-galaxy'));
  if (state.user) await enterGame();
}

/* ============================================================
   navigation entre vues
   ============================================================ */

function showView(name) {
  ['login', 'pick', 'command', 'moderation'].forEach((v) => {
    $(`#view-${v}`).classList.toggle('hidden', v !== name);
  });
  if (name !== 'command') stopTimers();
}

/* ============================================================
   modération de galaxie

   Les réglages décident des durées et des rendements : tout joueur peut les
   lire, seul un modérateur de la galaxie peut les changer. La vue n'affiche
   donc pas un formulaire au hasard — elle affiche celui que le serveur décrit,
   bornes comprises, et se met en lecture seule quand `can_edit` est faux.
   ============================================================ */

/* Relu à chaque changement de galaxie : le droit de modérer se porte sur une
   galaxie, pas sur un compte. */
async function refreshModeration() {
  state.moderation = null;
  if (!state.galaxy) {
    applyModerationAccess();
    return;
  }

  try {
    state.moderation = await api.galaxySettings(state.galaxy);
  } catch (e) {
    /* Réglages illisibles : la partie reste jouable, le bouton reste caché. */
    state.moderation = null;
  }
  applyModerationAccess();
}

function applyModerationAccess() {
  const allowed = !!(state.moderation && state.moderation.can_edit);
  ['#btn-moderation', '#pick-moderation'].forEach((sel) => {
    const el = $(sel);
    if (el) el.classList.toggle('hidden', !allowed);
  });
}

async function openModeration() {
  if (!state.galaxy) return;

  stopTimers();
  showView('moderation');
  $('#mod-error').classList.add('hidden');
  $('#mod-fields').innerHTML = '<p class="empty">Chargement…</p>';

  try {
    state.moderation = await api.galaxySettings(state.galaxy);
  } catch (e) {
    handleApiError(e, 'Réglages indisponibles');
    return;
  }

  renderModeration();
  applyModerationAccess();
}

function renderModeration(values = null) {
  const data = state.moderation;
  if (!data) return;

  const settings = values || data.settings || {};
  const editable = !!data.can_edit;

  $('#mod-galaxy').textContent = data.galaxy_name || state.galaxy || '—';

  const moderators = Array.isArray(data.moderators) ? data.moderators : [];
  $('#mod-moderators').innerHTML = moderators.length
    ? `<span class="dep"><span class="ov">Modérateurs</span><span>${esc(
        moderators.join(', ')
      )}</span></span>`
    : `<span class="dep"><span class="ov">Modérateurs</span><span>aucun</span></span>`;

  const updated = parseUtc(data.updated_at);
  $('#mod-updated').textContent = updated
    ? `Modifié le ${updated.toLocaleString()}`
    : 'Jamais modifié';

  $('#mod-fields').innerHTML = (data.parameters || [])
    .map((parameter) => {
      const value = settings[parameter.key];
      const isDefault = Number(value) === Number(parameter.default);
      return `<div class="mod-field">
        <div class="mod-field__head">
          <label for="mod-${esc(parameter.key)}">${esc(parameter.label)}</label>
          <span class="kb">${esc(parameter.key)}</span>
        </div>
        <p class="mod-field__help">${esc(parameter.description)}</p>
        <div class="mod-field__row">
          <input id="mod-${esc(parameter.key)}" name="${esc(parameter.key)}" type="number"
                 value="${esc(value)}" step="${esc(parameter.step)}"
                 min="${esc(parameter.min)}" max="${esc(parameter.max)}"
                 ${editable ? '' : 'disabled'}>
          <span class="mod-field__bounds">${esc(parameter.min)} – ${esc(parameter.max)}</span>
          <span class="mod-field__state">${
            isDefault ? 'valeur par défaut' : `défaut ${esc(parameter.default)}`
          }</span>
        </div>
      </div>`;
    })
    .join('');

  $('#mod-save').classList.toggle('hidden', !editable);
  $('#mod-reset').classList.toggle('hidden', !editable);
}

/* Le formulaire entier part à chaque enregistrement : le serveur ignore ce qui
   n'a pas bougé et efface ce qui revient au défaut. */
function readModerationForm() {
  const data = state.moderation;
  const values = {};
  (data.parameters || []).forEach((parameter) => {
    const field = $(`#mod-${parameter.key}`);
    if (field) values[parameter.key] = Number(field.value);
  });
  return values;
}

async function saveModeration(values) {
  const err = $('#mod-error');
  const btn = $('#mod-save');
  err.classList.add('hidden');
  btn.disabled = true;
  btn.textContent = 'Enregistrement…';

  try {
    const saved = await api.saveGalaxySettings(state.galaxy, values);
    state.moderation = Object.assign({}, state.moderation, saved);
    renderModeration();
    toast(`Réglages de ${state.galaxy} enregistrés.`, 'info', 'Modération');
  } catch (e) {
    err.textContent = e instanceof ApiError ? e.message : 'Enregistrement impossible';
    err.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Enregistrer';
  }
}

function leaveModeration() {
  if (state.territoryId) {
    showView('command');
    startTimers();
    reloadTerritory(true);
    return;
  }
  renderPicker();
  showView('pick');
}

function initModeration() {
  $('#mod-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    saveModeration(readModerationForm());
  });

  $('#mod-reset').addEventListener('click', () => {
    const data = state.moderation;
    if (!data) return;
    /* Remise à zéro explicite : on envoie les défauts, le serveur efface les
       réglages plutôt que d'enregistrer des valeurs qui ne changent rien. */
    renderModeration(data.defaults || {});
    saveModeration(Object.assign({}, data.defaults || {}));
  });

  $('#mod-back').addEventListener('click', leaveModeration);
  $('#btn-moderation').addEventListener('click', openModeration);
  $('#pick-moderation').addEventListener('click', openModeration);
}

/* ============================================================
   login
   ============================================================ */

function initLogin() {
  $('#login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('#login-submit');
    const err = $('#login-error');
    err.classList.add('hidden');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    try {
      const chosen = $('#login-galaxy').value;
      if (chosen) {
        state.galaxy = chosen;
        syncUrl();
      }
      state.user = await api.login($('#login-user').value.trim(), $('#login-pass').value);
      $('#login-pass').value = '';
      await enterGame();
    } catch (e) {
      err.textContent = e instanceof ApiError ? e.message : 'Connexion impossible';
      err.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Se connecter';
    }
  });
}

async function logout() {
  stopTimers();
  try {
    await api.logout();
  } catch (e) {
    /* la session locale est de toute façon abandonnée */
  }
  state.user = null;
  state.territory = null;
  state.territoryId = null;
  showView('login');
}

/* ============================================================
   sélection de territoire
   ============================================================ */

function renderPicker() {
  const list = $('#pick-list');
  $('#pick-sub').textContent = state.myTerritories.length
    ? 'Choisissez le territoire à administrer.'
    : `Aucun territoire ne vous est attribué dans ${state.galaxy || 'cette galaxie'}.`;

  if (!state.myTerritories.length) {
    list.innerHTML = `<p class="empty">Aucun territoire attribué à ${esc(
      (state.user && state.user.username) || 'ce compte'
    )} dans ${esc(state.galaxy || 'cette galaxie')}.<br>
    Réclamez une planète depuis le client de jeu, ou choisissez une autre galaxie ci-contre.</p>
    <button class="menu-btn menu-btn--dgr" data-action="logout">Déconnexion <span class="kb">ESC</span></button>`;
    return;
  }

  list.innerHTML =
    state.myTerritories
      .map(
        (t, i) => `<button class="menu-btn" data-territory="${t.id}">
        ${esc(territoryLabel(t))}
        <span class="kb">${esc(
          [galaxyOf(t), (t.system && t.system.name) || `SYS ${t.system ? t.system.id : '—'}`]
            .filter(Boolean)
            .join(' · ')
        )}</span>
      </button>`
      )
      .join('') +
    `<button class="menu-btn menu-btn--dgr" data-action="logout">Déconnexion <span class="kb">ESC</span></button>`;
}

/* Un territoire appartient a un systeme, qui appartient a une galaxie. Le
   serveur remonte `galaxy_name` a la racine ; `system.galaxy` reste le repli
   pour les charges utiles plus anciennes. */
function galaxyOf(t) {
  if (!t) return null;
  return t.galaxy_name || (t.system && t.system.galaxy) || null;
}

function territoryLabel(t) {
  if (t.name) return t.name;
  if (t.characteristics && t.characteristics.name) return t.characteristics.name;
  const sys = (t.system && t.system.name) || `Système ${t.system ? t.system.id : '?'}`;
  return `${sys} · orbite ${roman(t.position || 1)}`;
}

function territorySubtitle(t) {
  if (t.archetype_label) return t.archetype_label;
  const scheme = t.characteristics && t.characteristics.planeteScheme;
  return scheme ? humanize(scheme) : 'Territoire';
}

/* Le profil de gisements : le rendement réel de CE monde, archétype x veines.
   C'est ce qui distingue deux planètes du même type. */
function renderDeposits() {
  const host = $('#terr-deposits');
  const yields = (state.territory && state.territory.yields) || {};
  const richness = (state.territory && state.territory.deposits) || {};
  const entries = Object.entries(yields).sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    host.innerHTML = '<span>Aucun gisement exploitable sur ce monde.</span>';
    return;
  }

  host.innerHTML =
    '<span>Gisements</span>' +
    entries
      .map(([key, factor]) => {
        const meta = RESOURCE_BY_KEY[key];
        // Au-delà du plafond de tirage ordinaire (1.25), c'est une veine riche.
        const rich = (richness[key] || 1) > 1.3;
        return `<span style="--dep-accent:var(--res-${esc(key)})" title="${esc(
          (meta && meta.label) || key
        )}">
        <b>${esc((meta && meta.label) || humanize(key))}</b>
        <span class="${rich ? 'rich' : ''}">×${esc(factor.toFixed(2))}${rich ? ' veine riche' : ''}</span>
      </span>`;
      })
      .join('');
}

/* ============================================================
   scène système
   ============================================================ */

async function selectTerritory(id) {
  state.territoryId = id;
  state.tab = 'buildings';
  settledEvents = new Set();
  showView('command');
  $('#tab-body').innerHTML = '<p class="empty">Chargement…</p>';
  await reloadTerritory(true);
  startTimers();
}

/* `force` : un changement de territoire ou une action doit passer même si
   une requête périodique est encore en vol. */
async function reloadTerritory(force = false) {
  const id = state.territoryId;
  if (!id) return;
  if (reloading && !force) return;
  reloading = true;
  try {
    await doReloadTerritory(id);
  } finally {
    reloading = false;
  }
}

async function doReloadTerritory(id) {
  let territory;
  try {
    territory = await api.territory(id);
  } catch (e) {
    handleApiError(e, 'Territoire indisponible');
    return;
  }

  /* Le reste est complémentaire : un échec ne doit pas vider la scène. */
  const [events, ships, defenses, systemTerritories] = await Promise.all([
    api.territoryEvents(id).catch(() => []),
    api.territoryShips(id).catch(() => []),
    api.territoryDefenses(id).catch(() => []),
    territory.system ? api.systemTerritories(territory.system.id).catch(() => []) : Promise.resolve([]),
  ]);

  /* Le territoire a pu changer pendant les allers-retours : ne rien peindre
     par-dessus la sélection courante. */
  if (id !== state.territoryId) return;

  state.territory = territory;
  state.events = Array.isArray(events) ? events : [];
  state.ships = Array.isArray(ships) ? ships : [];
  state.defenses = Array.isArray(defenses) ? defenses : [];
  state.systemTerritories = Array.isArray(systemTerritories) ? systemTerritories : [];

  renderCommand();
}

function handleApiError(e, context) {
  if (e instanceof ApiError && e.status === 401) {
    toast('Session expirée, reconnectez-vous.', 'err', 'Authentification');
    showView('login');
    return;
  }
  toast(e && e.message ? e.message : 'Erreur inattendue', 'err', context);
}

function renderCommand() {
  const t = state.territory;
  if (!t) return;

  // La galaxie surtitre le systeme : c'est la portee reelle du territoire.
  $('#galaxy-name').textContent = galaxyOf(t) || 'Système';
  $('#sys-name').textContent = (t.system && t.system.name) || `Système ${t.system ? t.system.id : '—'}`;
  $('#terr-title').textContent = `${territoryLabel(t)} · ${territorySubtitle(t)}`;
  const updated = parseUtc(t.updated_at);
  $('#terr-updated').textContent = updated ? `MAJ ${updated.toLocaleTimeString('fr-FR')}` : '';

  renderDeposits();
  renderResources();
  renderRail();
  renderTabs();
  renderTabBody();
}

/* ---------- bandeau de ressources ---------- */

function hourlyGains() {
  const totals = {};
  RESOURCES.forEach((r) => {
    totals[r.key] = 0;
  });
  Object.values((state.territory && state.territory.buildings) || {}).forEach((b) => {
    Object.entries(normalizeResourceMap(b.gain)).forEach(([k, v]) => {
      if (k in totals) totals[k] += v;
    });
  });
  return totals;
}

/* Douze ressources ne tiennent pas dans un bandeau lisible. On n'affiche un
   matériau que si le monde en produit ou s'il en reste en stock : la barre
   raconte alors ce qu'est la planète, au lieu d'aligner huit zéros. */
function visibleResources() {
  const res = (state.territory && state.territory.resources) || {};
  const yields = (state.territory && state.territory.yields) || {};
  return RESOURCES.filter(
    (r) => !r.material || yields[r.key] > 0 || (res[r.key] || 0) > 0
  );
}

function renderResources() {
  const res = (state.territory && state.territory.resources) || {};
  const yields = (state.territory && state.territory.yields) || {};
  const gains = hourlyGains();
  $('#res-grid').innerHTML = visibleResources()
    .map((r) => {
      const delta = gains[r.key] || 0;
      const barren = r.material && !(yields[r.key] > 0);
      const title = barren
        ? `${r.label} — non extractible sur ce monde`
        : r.label;
      return `<div class="chip${barren ? ' chip--barren' : ''}" style="--chip-accent:var(--res-${r.key})" title="${esc(title)}">
      <span class="k">${r.code}</span>
      <span class="v">${esc(fmtNumber(res[r.key] || 0))}</span>
      ${delta ? `<span class="d${delta < 0 ? ' neg' : ''}">${esc(fmtDelta(delta))}/h</span>` : ''}
    </div>`;
    })
    .join('');
}

/* ---------- rail d'orbites ---------- */

function renderRail() {
  const rail = $('#orbit-rail');
  const mine = new Set(state.myTerritories.map((t) => t.id));
  const list = state.systemTerritories.length ? state.systemTerritories : [state.territory];

  const orbs = [...list]
    .sort((a, b) => (a.position || 0) - (b.position || 0))
    .map((t) => {
      const owned = mine.has(t.id);
      const on = t.id === state.territoryId;
      return `<button class="orb${on ? ' on' : ''}${owned ? '' : ' foreign'}"
        data-orbit="${t.id}" data-owned="${owned ? '1' : '0'}"
        title="${esc(territoryLabel(t))}${owned ? '' : ' — hors de votre contrôle'}">
        <i style="background:${planetGradient(t.id || t.position || 1)}"></i>
        <b>${esc(roman(t.position || 1))}</b>
      </button>`;
    })
    .join('');

  rail.innerHTML = `<span class="ov" style="text-align:center">Orbites</span>${orbs}`;
}

/* ---------- onglets ---------- */

function renderTabs() {
  document.querySelectorAll('#tabs .tab').forEach((el) => {
    el.classList.toggle('on', el.dataset.tab === state.tab);
  });
}

function renderTabBody() {
  const host = $('#tab-body');
  if (state.tab === 'buildings') host.innerHTML = renderBuildings();
  else if (state.tab === 'shipyard') host.innerHTML = renderUnits('ship');
  else host.innerHTML = renderUnits('defense');
  updateProgressBars();
}

/* ---------- événements en cours ---------- */

function eventsOfType(type) {
  return state.events.filter((e) => bare(e.eventType) === type);
}

function eventFor(type, name) {
  return eventsOfType(type).find((e) => e.extraArgs && e.extraArgs.name === name) || null;
}

function eventProgress(ev) {
  const start = parseUtc(ev.createdAt);
  const end = parseUtc(ev.finishingAt);
  if (!start || !end) return { pct: 0, remaining: 0 };
  const total = end - start;
  const left = end - Date.now();
  if (total <= 0) return { pct: 100, remaining: 0 };
  return {
    pct: Math.min(100, Math.max(0, ((total - Math.max(0, left)) / total) * 100)),
    remaining: Math.max(0, left / 1000),
  };
}

function progressMarkup(ev, label) {
  if (!ev) return '';
  const { pct, remaining } = eventProgress(ev);
  return `<div class="bar" data-event="${ev.id}"><i style="width:${pct.toFixed(1)}%"></i></div>
    <div class="bar-label" data-event-label="${ev.id}">
      <span>${esc(label)}</span><span>${esc(fmtDuration(remaining))}</span>
    </div>`;
}

/* Rafraîchi chaque seconde sans rejouer le rendu complet. */
function updateProgressBars() {
  let justFinished = false;
  state.events.forEach((ev) => {
    const bar = document.querySelector(`.bar[data-event="${ev.id}"] i`);
    const label = document.querySelector(`[data-event-label="${ev.id}"] span:last-child`);
    if (!bar) return;
    const { pct, remaining } = eventProgress(ev);
    bar.style.width = `${pct.toFixed(1)}%`;
    if (label) label.textContent = fmtDuration(remaining);
    if (remaining <= 0 && !settledEvents.has(ev.id)) {
      settledEvents.add(ev.id);
      justFinished = true;
    }
  });
  return justFinished;
}

/* ---------- onglet Buildings ---------- */

function costMarkup(costs, resources) {
  return Object.entries(costs)
    .map(([key, value]) => {
      const meta = RESOURCES.find((r) => r.key === key);
      const affordable = (resources[key] || 0) >= value;
      return `<span class="cost${affordable ? '' : ' no'}">${esc(meta ? meta.label : humanize(key))} <b>${esc(
        fmtNumber(value)
      )}</b></span>`;
    })
    .join('');
}

function gainMarkup(gains) {
  return Object.entries(gains)
    .map(([key, value]) => {
      const meta = RESOURCES.find((r) => r.key === key);
      return `<span class="cost yield">${esc(meta ? meta.label : humanize(key))} <b>${esc(
        fmtDelta(value)
      )} / h</b></span>`;
    })
    .join('');
}

function renderBuildings() {
  const t = state.territory;
  const buildings = t.buildings || {};
  const resources = t.resources || {};
  const names = Object.keys(buildings).sort();
  if (!names.length) return '<p class="empty">Aucun bâtiment sur ce territoire.</p>';

  return names
    .map((name) => {
      const b = buildings[name];
      const costs = normalizeResourceMap(b.cost);
      const gains = normalizeResourceMap(b.gain);
      const affordable = Object.entries(costs).every(([k, v]) => (resources[k] || 0) >= v);
      const ev = eventFor('building', name);
      const cls = ev ? 'row busy' : affordable ? 'row' : 'row off';

      return `<div class="${cls}">
      <div class="ico">${icon(name)}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(humanize(name))}</span>
          <span class="lvl">LVL ${esc(b.level)}</span>
          <button class="btn btn--sm${affordable && !ev ? ' btn--pri' : ''}"
            data-build-building="${esc(name)}" ${ev || !affordable ? 'disabled' : ''}>
            ${ev ? 'En cours' : 'Upgrade'}
          </button>
        </div>
        <div class="costs">
          ${costMarkup(costs, resources)}
          ${gainMarkup(gains)}
          <span class="cost">Durée <b>${esc(fmtDuration(b.duration))}</b></span>
        </div>
        <p class="desc">${esc(BUILDING_DESC[name] || 'Structure planétaire.')}</p>
        ${progressMarkup(ev, `Niveau ${Number(b.level) + 1} en construction`)}
      </div>
    </div>`;
    })
    .join('');
}

/* ---------- onglets Shipyard / Orbital Defences ---------- */

function renderUnits(kind) {
  const t = state.territory;
  const resources = t.resources || {};
  const catalog = kind === 'ship' ? state.catalog.ships : state.catalog.defenses;
  const owned = kind === 'ship' ? state.ships : state.defenses;

  if (!catalog || !catalog.length) {
    return '<p class="empty">Catalogue indisponible.</p>';
  }

  const counts = {};
  (owned || []).forEach((u) => {
    counts[u.type] = u.quantity;
  });

  const shipyardLevel = ((t.buildings || {}).shipyard || {}).level || 0;

  return catalog
    .map((u) => {
      const costs = normalizeResourceMap(u.cost);
      const affordable = Object.entries(costs).every(([k, v]) => (resources[k] || 0) >= v);
      const ev = eventFor(kind, u.name);
      /* Purement informatif : `Territory.build` ne vérifie que le coût,
         pas les prérequis technologiques. On n'interdit donc rien ici. */
      const locked = describeRequirements(u.requirements);
      const cls = ev ? 'row busy' : affordable ? 'row' : 'row off';
      const unitSeconds = u.integrity ? (u.integrity / 2500) * (1 + shipyardLevel) * 60 : 0;

      return `<div class="${cls}">
      <div class="ico">${icon(u.name)}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(humanize(u.name))}</span>
          <span class="lvl">×${esc(fmtNumber(counts[u.name] || 0))}</span>
          <input class="qty" type="number" min="1" max="999" value="1"
            data-qty="${esc(u.name)}" aria-label="Quantité ${esc(humanize(u.name))}">
          <button class="btn btn--sm${affordable ? ' btn--pri' : ''}"
            data-build-unit="${esc(u.name)}" data-kind="${kind}" ${affordable ? '' : 'disabled'}>
            Construire
          </button>
        </div>
        <div class="costs">
          ${costMarkup(costs, resources)}
          <span class="cost">Intégrité <b>${esc(fmtNumber(u.integrity || 0))}</b></span>
          ${unitSeconds ? `<span class="cost">Unité <b>${esc(fmtDuration(unitSeconds))}</b></span>` : ''}
        </div>
        <p class="desc">${esc(
          locked || `Coût unitaire. La durée d'assemblage dépend du niveau du chantier (LVL ${shipyardLevel}).`
        )}</p>
        ${progressMarkup(ev, `${(ev && ev.extraArgs && ev.extraArgs.quantity) || ''} restant(s) en assemblage`)}
      </div>
    </div>`;
    })
    .join('');
}

function describeRequirements(req) {
  if (!req || !req.technologies) return null;
  const parts = Object.entries(req.technologies).map(([k, v]) => `${humanize(k)} ${v}`);
  return parts.length ? `Requiert : ${parts.join(', ')}.` : null;
}

/* ============================================================
   actions
   ============================================================ */

async function upgradeBuilding(name) {
  try {
    await api.upgradeBuilding(state.territoryId, name);
    toast(`${humanize(name)} : construction lancée.`, 'info', 'Chantier');
    await reloadTerritory(true);
  } catch (e) {
    handleApiError(e, 'Construction refusée');
  }
}

async function buildUnit(kind, name, quantity) {
  const qty = Math.max(1, Math.min(999, Number(quantity) || 1));
  try {
    if (kind === 'ship') await api.buildShips(state.territoryId, name, qty);
    else await api.buildDefenses(state.territoryId, name, qty);
    toast(`${qty} × ${humanize(name)} : assemblage lancé.`, 'info', 'Chantier');
    await reloadTerritory(true);
  } catch (e) {
    handleApiError(e, 'Assemblage refusé');
  }
}

/* ============================================================
   minuteries
   ============================================================ */

function startTimers() {
  stopTimers();
  /* barres de progression : local, une fois par seconde */
  tickTimer = setInterval(() => {
    if (updateProgressBars()) reloadTerritory();
  }, 1000);
  /* état serveur : toutes les 30 s, pour les ressources produites */
  pollTimer = setInterval(reloadTerritory, 30000);
}

function stopTimers() {
  if (tickTimer) clearInterval(tickTimer);
  if (pollTimer) clearInterval(pollTimer);
  tickTimer = null;
  pollTimer = null;
}

/* ============================================================
   câblage
   ============================================================ */

function initEvents() {
  $('#tabs').addEventListener('click', (ev) => {
    const tab = ev.target.closest('.tab');
    if (!tab) return;
    state.tab = tab.dataset.tab;
    renderTabs();
    renderTabBody();
  });

  $('#orbit-rail').addEventListener('click', (ev) => {
    const orb = ev.target.closest('.orb');
    if (!orb) return;
    if (orb.dataset.owned !== '1') {
      toast("Ce territoire n'est pas sous votre contrôle.", 'err', 'Orbite');
      return;
    }
    const id = Number(orb.dataset.orbit);
    if (id !== state.territoryId) selectTerritory(id);
  });

  $('#tab-body').addEventListener('click', (ev) => {
    const building = ev.target.closest('[data-build-building]');
    if (building) {
      upgradeBuilding(building.dataset.buildBuilding);
      return;
    }
    const unit = ev.target.closest('[data-build-unit]');
    if (unit) {
      const name = unit.dataset.buildUnit;
      const input = document.querySelector(`[data-qty="${CSS.escape(name)}"]`);
      buildUnit(unit.dataset.kind, name, input ? input.value : 1);
    }
  });

  $('#pick-list').addEventListener('click', (ev) => {
    const pick = ev.target.closest('[data-territory]');
    if (pick) {
      selectTerritory(Number(pick.dataset.territory));
      return;
    }
    if (ev.target.closest('[data-action="logout"]')) logout();
  });

  $('#login-galaxy').addEventListener('change', (ev) => {
    state.galaxy = ev.target.value || null;
    syncUrl();
    fillGalaxySelect($('#pick-galaxy'));
  });
  $('#pick-galaxy').addEventListener('change', (ev) => switchGalaxy(ev.target.value));

  // Retour arriere du navigateur : l'URL fait foi.
  window.addEventListener('popstate', () => {
    const wanted = galaxyFromUrl();
    if (wanted && wanted !== state.galaxy) switchGalaxy(wanted);
  });

  $('#btn-refresh').addEventListener('click', () => reloadTerritory(true));
  $('#btn-logout').addEventListener('click', () => logout());
  $('#btn-switch').addEventListener('click', () => {
    stopTimers();
    renderPicker();
    showView('pick');
  });
}

/* ============================================================
   démarrage
   ============================================================ */

async function enterGame() {
  // Le droit de moderer se porte sur une galaxie : il se relit a chaque
  // entree, pas une fois pour la session.
  const [territories, catalog] = await Promise.all([
    api.myTerritories(state.galaxy).catch(() => []),
    api.catalog().catch(() => ({ ships: [], defenses: [] })),
    refreshModeration(),
  ]);
  state.myTerritories = territories;
  state.catalog = catalog || { ships: [], defenses: [] };

  if (territories.length === 1) {
    await selectTerritory(territories[0].id);
  } else {
    renderPicker();
    showView('pick');
  }
}

async function boot() {
  initTheme();
  initLogin();
  initEvents();
  initModeration();

  // Route publique : la liste des galaxies s'obtient avant toute connexion,
  // ce qui permet de choisir la sienne sur l'ecran de login.
  await loadGalaxies();

  try {
    state.user = await api.me();
    await enterGame();
  } catch (e) {
    showView('login');
  }
}

boot();
