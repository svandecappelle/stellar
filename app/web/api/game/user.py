# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, serialize
from app.application import login_required

from app.models.game.technologies.technology import Technology


@app.route('/api/events', methods=['GET'])
@login_required
@serialize
def get_my_events():
    return Technology.all(user=current_user.get())


@app.route('/api/territories', methods=['GET'])
@login_required
@serialize
def get_territories():
    return current_user.get().territories

