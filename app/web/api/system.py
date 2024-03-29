# -*- coding: utf-8 -*-

from flask import abort
from flask_login import current_user
from werkzeug.exceptions import NotFound

from app.application import app, db, serialize, login_required
from app.models.user import User


@app.route('/api/user/<string:username>', methods=['GET'])
@login_required
@serialize(without_rights=True)
def get_user(username):
    """
    Get user object from its name
    ---
    :param username: username property
    :type username: str
    """
    if not User.exists(username=username):
        return NotFound(404, 'User does not exists')
    return User.get(username=username)


@app.route('/api/auth/me', methods=['GET'])
@login_required
@serialize(without_rights=False)
def me():
    """
    Get my own user
    """
    return User.get(username=current_user.get().username)
