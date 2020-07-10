# -*- coding: utf-8 -*-

from flask import jsonify, request, abort
from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required

from app.models.game.technologies.technology import Technology


@app.route('/api/technologies', methods=['GET'])
@login_required
@serialize
def get_my_technologies():
    return Technology.all(user=current_user.get())
