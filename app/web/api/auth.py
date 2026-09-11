# -*- coding: utf-8 -*-

"""
Inscription, et jetons d'appareil.

La connexion par identifiant et mot de passe vit dans `middleware.py` et n'a pas
bouge. Ce qui s'ajoute ici est ce qui evite de la refaire a chaque demarrage du
jeu :

    POST /api/users            creer un compte
    POST /api/auth/token       identifiants  → jeton d'appareil (+ session)
    POST /api/auth/session     jeton         → session
    GET  /api/auth/tokens      les appareils enregistres
    DELETE /api/auth/token/<id>  en deconnecter un
    DELETE /api/auth/tokens      les deconnecter tous

Pourquoi un jeton plutot que le cookie « se souvenir de moi » de Flask-Login,
qui existait deja : ce cookie n'est pas revocable, il est signe par la cle de
session — donc invalide des qu'elle tourne — et il vaut mot de passe jusqu'a son
echeance. Le jeton, lui, est une ligne en base : on peut la fermer, elle survit
a un changement de cle, et le serveur n'en garde que l'empreinte.

Le jeton n'authentifie AUCUNE route de jeu. Il n'ouvre qu'une session, et c'est
la session qui porte la suite : moins il circule, moins il a d'occasions de
fuir.
"""

from flask import jsonify, request, abort
from flask_login import login_user, current_user

from app.application import app, db, json_description, login_required, serialize
from app.models.audit import Action, record
from app.models.server import ServerSettings
from app.models.token import DeviceToken
from app.models.user import User
from app.security import WeakPassword, check_password_policy
from app.web.api.middleware import AuthUser
from app.web.api.throttle import TooManyAttempts, forget, hit
from logger import logger


#: Longueur d'un nom de compte. Trois pour laisser passer les noms courts, et un
#: plafond pour que la colonne ne serve pas de depotoir.
MIN_USERNAME = 3
MAX_USERNAME = 32


@app.errorhandler(TooManyAttempts)
def too_many_attempts(error):
    """
    429, et le nombre de secondes a attendre.
    ---
    Le client peut alors dire « reessayez dans une minute » au lieu d'un « echec »
    que le joueur relancerait aussitot.
    """
    response = jsonify({'message': str(error)})
    response.status_code = 429
    response.headers['Retry-After'] = str(error.retry_after)
    return response


# ── Inscription ─────────────────────────────────────────────────────────────

@app.route('/api/users', methods=['POST'])
@json_description(file='descriptions/authentication.json')
def register():
    """
    Cree un compte.
    ---
    Le compte nait SANS monde. C'est deliberatement le parcours existant qui
    prend la suite : le joueur reclame son premier monde tellurique par
    `POST /api/territory/<id>`, et c'est cette attribution-la qui pose son arbre
    technologique. Attribuer un monde ici priverait le joueur du choix, et
    ferait de l'inscription le seul endroit du serveur qui sache generer une
    situation de depart.
    """
    hit('register', limit=5, window=600)

    if not ServerSettings.value('registration_open'):
        # 403 et non 503 : le serveur va tres bien, il a decide de ne pas
        # accepter de compte. La console lit le meme reglage sur `/api/server`
        # et cesse de proposer l'inscription — ceci est la barriere, cela
        # n'etait que la politesse.
        return abort(403, "Registration is closed on this server.")

    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password')
    email = (payload.get('email') or '').strip()

    if len(username) < MIN_USERNAME or len(username) > MAX_USERNAME:
        return abort(400, "The name must be between %d and %d characters long."
                     % (MIN_USERNAME, MAX_USERNAME))

    if '@' not in email or len(email) < 5:
        # Aucune verification par courriel : rien n'envoie de message ici. Le
        # champ sert a retrouver un compte, et pretendre le verifier serait
        # mentir sur ce que le serveur fait.
        return abort(400, "A valid email address is required.")

    try:
        check_password_policy(password)
    except WeakPassword as weak:
        return abort(400, str(weak))

    if User.exists(username=username):
        # Le nom est visible de tous une fois en jeu : le refus ne revele donc
        # rien qu'une partie ne montre deja.
        return abort(409, "That name is taken.")

    # `User.new` vide la session : l'identifiant existe donc deja, et la trace
    # peut partir AVANT la validation. L'ordre compte — une ligne d'audit posee
    # apres le `commit` ne serait validee par personne, et la session `scoped`
    # rendue en fin de requete l'emporterait. En test, ou la session survit a la
    # requete, cela ne se verrait pas.
    user = User.new(username=username, password=password, email=email)

    logger.info("Account created", infos=dict(user_id=user.id))
    record(Action.REGISTER, user_id=user.id, username=user.username, email=email)

    db.session.commit()

    # La session s'ouvre dans la foulee : demander au joueur de se reconnecter
    # juste apres s'etre inscrit n'apporte rien.
    login_user(AuthUser(username=user.username))

    response = jsonify(user.serialize())
    response.status_code = 201
    return response


# ── Jetons d'appareil ───────────────────────────────────────────────────────

@app.route('/api/auth/token', methods=['POST'])
@json_description(file='descriptions/authentication.json')
def issue_token():
    """
    Echange des identifiants contre un jeton d'appareil.
    ---
    C'est le seul endroit ou la valeur en clair existe : elle n'est nulle part
    en base, et cette reponse-ci est la derniere fois qu'on la voit. Un client
    qui la perd en redemande une, il ne la retrouve pas.

    Ouvre aussi la session, pour que la premiere connexion tienne en un aller-
    retour.
    """
    hit('login', limit=10, window=300)

    payload = request.get_json(silent=True) or {}
    username = payload.get('username')
    password = payload.get('password')

    if not username or not password:
        return abort(401, "Invalid credentials")

    if not User.exists(username=username):
        return abort(401, "Invalid credentials")

    user = User.get(username=username)
    if not user.check_password(password):
        return abort(401, "Invalid credentials")

    plain, token = DeviceToken.issue(user=user, label=payload.get('device'))

    # La valeur en clair n'est PAS journalisee — `record` la retirerait de toute
    # facon, mais on ne la lui donne pas. Seul l'identifiant de la ligne y va :
    # il suffit a rapprocher une emission de la revocation qui la suivra.
    record(Action.TOKEN_ISSUE, user_id=user.id, username=user.username,
           device_id=token.id, label=token.label)
    record(Action.LOGIN, user_id=user.id, username=user.username)

    db.session.commit()

    forget('login')
    login_user(AuthUser(username=user.username))

    return jsonify({
        'token': plain,
        'device': token.serialize,
        'user': user.serialize(),
    })


@app.route('/api/auth/session', methods=['POST'])
@json_description(file='descriptions/authentication.json')
def open_session():
    """
    Rouvre une session a partir d'un jeton d'appareil.
    ---
    Un jeton inconnu, revoque ou perime rendent le meme 401 : les distinguer
    renseignerait qui essaie des valeurs sur ce qui a existe.
    """
    hit('session', limit=30, window=300)

    payload = request.get_json(silent=True) or {}
    token = DeviceToken.resolve(payload.get('token'))
    if token is None:
        return abort(401, "Invalid token")

    # L'echeance est glissante : l'usage la repousse. Un joueur qui joue ne
    # revoit jamais le formulaire, une machine oubliee s'eteint toute seule.
    token.touch()
    record(Action.SESSION_OPEN, user_id=token.user_id,
           username=token.user.username, device_id=token.id)
    db.session.commit()

    forget('session')
    login_user(AuthUser(username=token.user.username))

    return jsonify({
        'device': token.serialize,
        'user': token.user.serialize(),
    })


@app.route('/api/auth/tokens', methods=['GET'])
@login_required
@json_description(file='descriptions/authentication.json')
def list_tokens():
    """Les appareils qui peuvent ouvrir une session sur ce compte."""
    me = current_user.get()
    return jsonify({
        'devices': [token.serialize for token in DeviceToken.alive(user=me)],
    })


@app.route('/api/auth/token/<int:token_id>', methods=['DELETE'])
@login_required
@json_description(file='descriptions/authentication.json')
def revoke_token(token_id):
    """
    Deconnecte un appareil.
    ---
    Un jeton qui n'est pas le sien rend 404 et non 403 : repondre « interdit »
    confirmerait qu'il existe.
    """
    me = current_user.get()

    token = next((t for t in DeviceToken.of(user=me) if t.id == token_id), None)
    if token is None:
        return abort(404, "No such device.")

    token.revoke()
    record(Action.TOKEN_REVOKE, device_id=token.id, label=token.label)
    db.session.commit()
    return jsonify(token.serialize)


@app.route('/api/auth/tokens', methods=['DELETE'])
@login_required
@json_description(file='descriptions/authentication.json')
def revoke_all_tokens():
    """Deconnecte tous les appareils, y compris celui qui le demande."""
    me = current_user.get()
    closed = DeviceToken.revoke_all(user=me)
    record(Action.TOKEN_REVOKE, devices=closed, scope='all')
    db.session.commit()
    return jsonify({'revoked': closed})
