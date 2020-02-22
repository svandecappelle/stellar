# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g, abort
from flask_login import login_user, logout_user, current_user
from app.application import app, User
from app.application import login_required


class AuthenticationError(ex.HTTPException):
    code = 400
    description = '<p>Invalid credentials</p>'


@app.errorhandler(AuthenticationError)
def invalid_credentials(e):
    return e.description, e.code


@app.route('/api/auth', methods=['GET'])
@login_required
def get_user_logged():
    return jsonify({'token': 'token', 'duration': 600, 'user': {'uid': 'uid'}, 'connected': True})


@app.route('/api/auth/login', methods=['GET', 'POST'])
def autentication():
    # Yet in dev
    if not request.json.get("username"):
        logout_user()
        return abort(400, "Invalid credentials")
    remember = request.json.get('remember_me', False)
    login_user(User(request.json['username']), remember=remember)
    return jsonify({'token': 'token', 'duration': 600, 'user': {'uid': 'uid'}, 'connected': True})


@app.route('/api/auth/logout', methods=['GET', 'POST'])
def logout():
    session['logged_in'] = False
    return jsonify({'message': 'ok'})


@app.route('/api/resource')
def get_resource():
    return jsonify({'data': 'Hello, %s!' % g.user.username})
