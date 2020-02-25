# -*- coding: utf-8 -*-

from flask import abort
from flask_login import current_user

from app.application import app, db, serialize, login_required
from app.models.user import User


@app.route('/api/user/<string:username>', methods=['GET'])
@login_required
@serialize
def get_user(username):
    """
    Get user object from its name
    ---
    :param username: username property
    :type username: str
    """
    if not User.exists(session=db.session, username=username):
        return abort(404, 'User does not exists')
    return User.get(session=db.session, username=username)


@app.route('/api/auth/me', methods=['GET'])
@login_required
def me():
    """
    Get my own user
    """
    return User.get(session=db.session, username=current_user.get().username).serialize(without_rights=False)
