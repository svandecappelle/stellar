# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g

from app.application import app
from app.application import login_required

from app.models.game.system import System


@app.route('/api/system/{}', methods=['GET'])
@login_required
def get_system_detail(id):
    system = System.get(id)
    return system

@app.route('/api/system/{}/army', methods=["GET"])
@login_required
def get_system_army(id):
    system = System.get(id)
    return system.army
