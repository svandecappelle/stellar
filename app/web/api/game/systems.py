# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g

from app.application import app, db, serialize
from app.application import login_required

from app.models.game.system import System
from app.models.game.territory import Territory

# TODO apply check user has access to the system/territory

@app.route('/api/system/<int:id>', methods=['GET'])
@serialize
def get_system_detail(id):
    system = System.get(id=id)
    return system


@app.route('/api/system/<int:id>', methods=['POST'])
@login_required
@serialize
def create_system(id):
    system = System.get(id=id)
    territories = request.json.get('territories')
    if system.territories:
        raise ex.Conflict("System already exists")
    for t in territories:
        if not t.get('characteristics'):
            raise ex.BadRequest("Territory characteristics is required")
        Territory.create(
            system_id=system.id,
            position_in_system=t.get('position'),
            characteristics=t.get('characteristics'),
        )
    db.session.commit()
    return system


@app.route('/api/system/<int:id>/territories', methods=['GET'])
@serialize
def get_system_territories(id):
    system = System.get(id=id)
    return {
        "id": system.id,
        "territories": system.territories
    }


@app.route('/api/territory/<int:id>', methods=['GET'])
@serialize
def get_territory_detail(id):
    territory = Territory.get(id=id)
    return territory


@app.route('/api/system/<int:id>/army', methods=["GET"])
@login_required
@serialize
def get_system_army(id):
    system = System.get(id=id)
    return system.army
