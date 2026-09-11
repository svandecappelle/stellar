# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g, abort
from flask_login import UserMixin, login_user, logout_user, current_user
from app.application import app, db, json_description, login_required, serialize
from app.models.audit import Action, record
from app.models.user import User


class AuthUser(UserMixin, User):
    def __init__(self, username):
        self.id = username

    def get(self):
        if self.is_authenticated:
            return User.get(username=self.id)
        return None


class AuthenticationError(ex.HTTPException):
    code = 400
    description = '<p>Invalid credentials</p>'


@app.errorhandler(AuthenticationError)
def invalid_credentials(e):
    return e.description, e.code


@app.route('/api/auth', methods=['GET'])
@login_required
@serialize(without_rights=False)
@json_description(file='descriptions/authentication.json')
def get_user_logged():
    return current_user.get()


@app.route('/api/auth/login', methods=['GET', 'POST'])
@serialize(without_rights=True)
@json_description(file='descriptions/authentication.json')
def authentication():
    """
    Ouvre une session a partir d'un identifiant et d'un mot de passe.
    ---
    Un seul message de refus pour les trois cas — nom vide, compte inconnu,
    mot de passe faux. Distinguer « ce compte n'existe pas » de « ce n'est pas
    le bon mot de passe » revient a offrir la liste des comptes du serveur a
    qui prend la peine de la demander.
    """
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        logout_user()
        return abort(401, "Invalid credentials")

    if not User.exists(username=username):
        return abort(401, "Invalid credentials")

    user = User.get(username=username)
    if not user.check_password(password):
        return abort(401, "Invalid credentials")

    # `check_password` a pu remplacer une empreinte SHA-256 par une empreinte
    # scrypt : cette conversion-la n'a lieu qu'une fois par compte, et la perdre
    # la ferait recommencer a chaque connexion.
    record(Action.LOGIN, user_id=user.id, username=user.username)
    db.session.commit()

    login_user(AuthUser(
        username=user.username,
    ), remember=payload.get('remember_me', False))
    return current_user.get()


@app.route('/api/auth/logout', methods=['GET', 'POST'])
@json_description(file='descriptions/authentication.json')
def logout():
    """
    Ferme la session du joueur.
    ---
    Elle ne la fermait pas : elle posait `logged_in = False`, un drapeau que
    personne ne lit, et laissait intacte la session de Flask-Login. Le cookie de
    session et celui de « se souvenir de moi » — pose a la connexion, que le
    client demande toujours — survivaient donc a la deconnexion, et la requete
    suivante repartait authentifiee.

    L'ordre compte : `logout_user` retire les cles de Flask-Login et, pour
    effacer le cookie de memorisation, pose `_remember = 'clear'` dans la
    session. Vider la session apres cet appel emporterait ce drapeau avec le
    reste, et le cookie resterait chez le client.
    """
    # Notee AVANT la fermeture : apres, `current_user` ne dit plus qui
    # partait, et la ligne s'ecrirait sans nom.
    record(Action.LOGOUT)
    db.session.commit()

    session.pop('logged_in', None)
    logout_user()
    return jsonify({'message': 'ok'})


@app.route('/api/resource')
@json_description(file='descriptions/authentication.json')
def get_resource():
    return jsonify({'data': 'Hello, %s!' % g.user.username})
