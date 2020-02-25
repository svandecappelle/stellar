# -*- coding: utf-8 -*-

from Crypto.Hash import SHA256
import werkzeug.exceptions as ex
from flask import jsonify, request, session, g, abort
from flask_login import UserMixin, login_user, logout_user, current_user
from app.application import app, login_required, serialize
from app.models import User


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
def get_user_logged():
    return current_user.get()


@app.route('/api/auth/login', methods=['GET', 'POST'])
@serialize(without_rights=True)
def authentication():
    # Yet in dev
    if not request.json.get("username") or not request.json.get("username"):
        logout_user()
        return abort(401, "Invalid credentials")
    remember = request.json.get('remember_me', False)
    username = request.json['username']
    password = request.json['password']

    if not User.exists(username=username):
        return abort(401, "Invalid credentials")
    user = User.get(username=username)
    given = SHA256.new()
    given.update(password.encode('utf-8'))
    if given.digest() != user.password:
        return abort(401, "Invalid credentials")

    login_user(AuthUser(
        username=user.username,
    ), remember=remember)
    return current_user.get()


@app.route('/api/auth/logout', methods=['GET', 'POST'])
def logout():
    session['logged_in'] = False
    return jsonify({'message': 'ok'})


@app.route('/api/resource')
def get_resource():
    return jsonify({'data': 'Hello, %s!' % g.user.username})
