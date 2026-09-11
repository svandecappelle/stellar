# -*- coding: utf-8 -*-

"""
L'administration du serveur : sa version de schema, ses reglages, son journal.

    GET  /api/admin/schema     ou en est la base face aux migrations du depot
    GET  /api/admin/settings   les reglages, leur description et leurs bornes
    POST /api/admin/settings   en changer
    GET  /api/admin/audit      le journal, filtre et pagine
    POST /api/admin/audit/purge  effacer les lignes anciennes
    GET  /api/server           ce qu'un visiteur non connecte doit savoir

Qui peut entrer
---------------
Le role `admin`, et lui seul. Pas le moderateur : sa portee est une galaxie,
c'est-a-dire une partie, et regler le serveur ou lire ce que TOUS les joueurs
ont fait deborde largement de la partie qu'il arbitre. La verification est une
decoration posee sur chaque route plutot qu'un prefixe d'URL : un prefixe se
contourne en ajoutant une route au mauvais endroit, une decoration oubliee se
voit a la relecture.

Pourquoi la version de schema est reservee
-------------------------------------------
Elle ne sert a personne d'autre. Annoncer publiquement « cette base est a la
revision 3ab7d1f65c92 » dit a qui passe quelles colonnes existent et lesquelles
manquent — c'est-a-dire quelles anomalies esperer. `/api/mon/ping` reste la
route publique qui dit que le serveur est debout, et c'est tout ce qu'une
supervision a besoin de savoir de l'exterieur.
"""

from functools import wraps

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy import create_engine

import schema_version
from app.application import app, db, dburi, json_description, login_required
from app.models.audit import Action, AuditLog, OK, prune, record
from app.models.role import RoleType
from app.models.server import DEFAULTS, SETTINGS, ServerSettings
from app.models.user import User
from app.web.api.exceptions import BadRequestError, PermissionDeniedError


#: Lignes de journal par page. Cinquante tiennent dans un ecran sans defiler
#: longtemps, et une page plus large ferait transiter des charges utiles que
#: personne ne lit.
PAGE = 50
MAX_PAGE = 500


def admin_required(func):
    """
    Reserve la route aux administrateurs.

    Pose APRES `login_required` dans la pile de decorateurs, donc ecrite en
    dessous : sans session ouverte, `current_user.get()` ne rend personne et la
    reponse serait un 403 la ou 401 est juste.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        user = current_user.get()
        if user is None or not user.has_role(RoleType.admin):
            # Le refus est journalise par l'`after_request` de `audit.py`, comme
            # tous les refus : une tentative d'entrer dans l'administration est
            # exactement le genre de ligne qu'on veut retrouver.
            raise PermissionDeniedError("Administrator access is required.")
        return func(*args, **kwargs)

    return wrapped


# ── Version du schema ───────────────────────────────────────────────────────

@app.route('/api/admin/schema', methods=['GET'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def schema_state():
    """
    Ou en est la base face aux migrations du depot.
    ---
    Deux revisions a rapprocher : celle que la base porte dans
    `alembic_version`, et la tete de la chaine sous `migrations/versions`. Quand
    elles different, le code tourne sur un schema qui n'est pas le sien, et cela
    ne se voit qu'au premier acces a une colonne absente — c'est-a-dire en
    pleine partie.

    Le moteur est construit ici plutot que repris de la session : la lecture
    d'`alembic_version` se fait hors de toute transaction de jeu, et une
    transaction cassee par ailleurs ne doit pas empecher de diagnostiquer.
    """
    engine = create_engine(dburi(), echo=False)
    try:
        state, current, head = schema_version.status(engine)
        pending = _pending(current, head)
    finally:
        engine.dispose()

    return jsonify({
        'state': state,
        'revision': current,
        'head': head,
        # Ce qui reste a jouer, du plus ancien au plus recent. Un administrateur
        # qui voit « 2 migrations en attente » et leurs noms sait ce qu'il
        # s'appreterait a appliquer.
        'pending': pending,
        'up_to_date': state == schema_version.UP_TO_DATE,
        'message': _schema_message(state, current, head),
        'command': 'docker compose --profile migrate run --rm migrate',
    })


def _pending(current, head):
    """
    Les revisions entre celle de la base et la tete, de la plus ancienne a la
    plus recente. Vide si la base est a jour, ou si l'on ne peut pas savoir.
    """
    if current == head:
        return []

    try:
        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(schema_version.MIGRATIONS_DIR)
        walked = []
        for revision in scripts.walk_revisions(base='base', head=head or 'head'):
            if revision.revision == current:
                break
            walked.append({
                'revision': revision.revision,
                'description': revision.doc or '',
            })
        # `walk_revisions` descend de la tete vers la base : on rend l'ordre
        # dans lequel les migrations se jouent.
        return list(reversed(walked))
    except Exception:  # noqa: BLE001 - un diagnostic ne doit pas lever
        return []


def _schema_message(state, current, head):
    if state == schema_version.UP_TO_DATE:
        return "Le schema est a jour."
    if state == schema_version.BEHIND:
        return ("La base est a la revision %s, le code attend %s. Jouez la "
                "migration avant de continuer." % (current, head))
    if state == schema_version.AHEAD:
        return ("La base porte la revision %s, que ce code ne connait pas. "
                "C'est le code qu'il faut mettre a jour, pas la base." % current)
    if state == schema_version.UNSTAMPED:
        return ("La base a des tables mais pas de `alembic_version` : aucune "
                "migration ne peut dire ce qui est deja applique.")
    return "Etat du schema indeterminable."


# ── Reglages du serveur ─────────────────────────────────────────────────────

@app.route('/api/admin/settings', methods=['GET'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def get_server_settings():
    """
    Les reglages, avec ce qu'il faut pour dessiner le formulaire.
    ---
    La description des parametres est servie avec les valeurs : la console
    construit son formulaire a partir de la, bornes comprises, plutot que de
    redire ce que le serveur sait deja.
    """
    row = ServerSettings.row()

    return jsonify({
        'settings': ServerSettings.effective(),
        'defaults': dict(DEFAULTS),
        'overrides': dict(row.overrides) if row and row.overrides else {},
        'parameters': [setting.serialize for setting in SETTINGS],
        'updated_at': row.updated_at.isoformat() if row and row.updated_at else None,
    })


@app.route('/api/admin/settings', methods=['POST', 'PUT'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def update_server_settings():
    """
    Change les reglages du serveur.
    ---
    Le corps accepte soit `{"settings": {...}}`, soit directement les cles : la
    console envoie le formulaire entier, un appel a la main n'en change souvent
    qu'une.

    Le changement est journalise avec les valeurs demandees. Un administrateur
    qui ouvre les inscriptions, laisse passer une vague de comptes puis les
    referme ne doit pas pouvoir le faire sans laisser de trace.
    """
    payload = request.get_json(silent=True) or {}
    wanted = payload.get('settings', payload)

    try:
        settings = ServerSettings.write(wanted=wanted)
    except ValueError as error:
        raise BadRequestError(message=str(error))

    record(Action.ADMIN_SETTINGS, outcome=OK, changed=wanted)
    db.session.commit()

    return jsonify({
        'settings': settings,
        'defaults': dict(DEFAULTS),
        'parameters': [setting.serialize for setting in SETTINGS],
    })


# ── Journal d'audit ─────────────────────────────────────────────────────────

@app.route('/api/admin/audit', methods=['GET'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def read_audit():
    """
    Le journal, du plus recent.
    ---
    Filtres, tous facultatifs et cumulables :

        ?user=<nom>       ce qu'a fait ce joueur — nom recopie, donc trouvable
                          meme si le compte a disparu
        ?action=<geste>   `auth.login`, `territory.build`, …
        ?outcome=ok|refused
        ?status=<code>    un code HTTP precis
        ?since=<ISO>      a partir de cette date
        ?page=<n>         a partir de 1

    Les lignes anciennes sont effacees au passage, selon
    `audit_retention_days`. Le faire ici plutot que dans une tache separee : le
    journal n'a pas besoin d'etre purge a la seconde, il a besoin de ne pas
    grossir sans fin, et l'ouverture de cette vue est un moment ou l'on peut se
    permettre une suppression.
    """
    _prune_quietly()

    query = db.session.query(AuditLog)

    username = (request.args.get('user') or '').strip()
    if username:
        query = query.filter(AuditLog.username == username)

    action = (request.args.get('action') or '').strip()
    if action:
        query = query.filter(AuditLog.action == action)

    outcome = (request.args.get('outcome') or '').strip()
    if outcome:
        query = query.filter(AuditLog.outcome == outcome)

    status = request.args.get('status')
    if status:
        try:
            query = query.filter(AuditLog.status == int(status))
        except (TypeError, ValueError):
            raise BadRequestError("status doit etre un code HTTP")

    since = (request.args.get('since') or '').strip()
    if since:
        query = query.filter(AuditLog.created_at >= _date(since))

    total = query.count()

    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    try:
        size = min(MAX_PAGE, max(1, int(request.args.get('size', PAGE))))
    except (TypeError, ValueError):
        size = PAGE

    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return jsonify({
        'entries': [row.serialize for row in rows],
        'total': total,
        'page': page,
        'size': size,
        'pages': max(1, (total + size - 1) // size),
        # De quoi peupler les listes de filtres sans que la console ait a
        # deviner le vocabulaire du serveur.
        'actions': Action.all(),
        'retention_days': ServerSettings.value('audit_retention_days'),
    })


@app.route('/api/admin/audit/purge', methods=['POST'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def purge_audit():
    """
    Efface les lignes plus vieilles que N jours.
    ---
    `{"days": 7}` pour couper plus court que la conservation reglee. La purge
    elle-meme est journalisee — c'est la seule ligne qu'un administrateur ne
    peut pas faire disparaitre sans laisser de trace de sa disparition.
    """
    payload = request.get_json(silent=True) or {}
    days = payload.get('days', ServerSettings.value('audit_retention_days'))

    try:
        days = int(days)
    except (TypeError, ValueError):
        raise BadRequestError("days doit etre un nombre de jours")

    if days < 1:
        raise BadRequestError("days doit valoir au moins 1")

    removed = prune(days=days)
    record(Action.ADMIN_PURGE, outcome=OK, days=days, removed=removed)
    db.session.commit()

    return jsonify({'removed': removed, 'days': days})


@app.route('/api/admin/players', methods=['GET'])
@login_required
@admin_required
@json_description(file='descriptions/admin.json')
def list_players():
    """
    Les comptes, pour le filtre du journal.
    ---
    Juste ce qu'il faut pour designer quelqu'un : un nom et un identifiant. La
    vue d'administration n'est pas une console de gestion de comptes, et servir
    ici tout ce qu'on sait d'un joueur serait une fuite gratuite.
    """
    rows = db.session.query(User.id, User.username).order_by(User.username).all()
    return jsonify({
        'players': [{'id': row[0], 'username': row[1]} for row in rows],
    })


# ── Ce qu'un visiteur voit avant de se connecter ────────────────────────────

@app.route('/api/server', methods=['GET'])
@json_description(file='descriptions/admin.json')
def server_public():
    """
    Ce qu'il faut savoir avant d'avoir un compte.
    ---
    Publique a dessein, et volontairement pauvre : le message d'accueil, et si
    les inscriptions sont ouvertes. Rien sur la version, le schema ou la
    charge — un visiteur non authentifie n'a aucune raison d'apprendre cela, et
    quelqu'un qui cherche une faille en a plusieurs.

    `registration_open` n'est ici qu'une politesse : il permet a la console de
    ne pas proposer un formulaire qui sera refuse. La barriere est dans
    `POST /api/users`.
    """
    return jsonify({
        'announcement': ServerSettings.value('announcement') or '',
        'registration_open': bool(ServerSettings.value('registration_open')),
    })


# ── Outillage ───────────────────────────────────────────────────────────────

def _prune_quietly():
    """
    Purge opportuniste. Ne leve jamais : une suppression qui echoue ne doit pas
    empecher de lire le journal — c'est meme le moment ou l'on en a le plus
    besoin.
    """
    try:
        removed = prune(days=ServerSettings.value('audit_retention_days'))
        if removed:
            db.session.commit()
    except Exception:  # noqa: BLE001
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _date(text):
    from datetime import datetime

    try:
        # `fromisoformat` n'accepte pas le « Z » terminal avant Python 3.11 ; la
        # console en envoie un, et le refuser rendrait le filtre inutilisable.
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except (TypeError, ValueError):
        raise BadRequestError("since doit etre une date ISO 8601")
