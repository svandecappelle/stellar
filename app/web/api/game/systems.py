# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g

from app.application import app, serialize
from app.application import login_required

from app.models.game.system import System


@app.route('/api/system/<int:id>', methods=['GET'])
@login_required
@serialize
def get_system_detail(id):
    system = System.get(id=id)
    return system


@app.route('/api/system/<int:id>/territories', methods=['GET'])
@login_required
@serialize
def get_system_territories(id):
    system = System.get(id=id)
    return {
        "id": system.id,
        "territories": system.territories
    }


@app.route('/api/system/<int:id>/army', methods=["GET"])
@login_required
@serialize
def get_system_army(id):
    system = System.get(id=id)
    return system.army
