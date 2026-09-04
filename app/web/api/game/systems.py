# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description

from app.models.game.system import System
from app.models.game.territory import Territory

# TODO apply check user has access to the system/territory

@app.route('/api/system/<int:id>', methods=['GET'])
@serialize
@json_description(file='descriptions/systems.json')
def get_system_detail(id):
    system = System.get(id=id)
    return system


@app.route('/api/system/<int:id>', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/systems.json')
def create_system(id):
    system = System.get(id=id)
    territories = request.json.get('territories')
    if system.territories:
        raise ex.Conflict("System already exists")
    for t in territories:
        if not t.get('characteristics'):
            raise ex.BadRequest("Territory characteristics is required")
        # Le client tire l'apparence de la planete, et l'apparence dit
        # l'archetype : une geante gazeuse n'est pas une planete tellurique.
        # Sans archetype fourni, le serveur en tire un lui-meme.
        Territory.create(
            system_id=system.id,
            position_in_system=t.get('position'),
            characteristics=t.get('characteristics'),
            archetype=t.get('archetype'),
            name=t.get('name'),
        )
    db.session.commit()
    return system


@app.route('/api/system/<int:id>/territories', methods=['GET'])
@serialize
@json_description(file='descriptions/systems.json')
def get_system_territories(id):
    system = System.get(id=id)
    return {
        "id": system.id,
        "territories": system.territories
    }


@app.route('/api/territory/<int:id>', methods=['GET'])
@serialize
@json_description(file='descriptions/territories.json')
def get_territory_detail(id):
    territory = Territory.get(id=id)
    return territory


@app.route('/api/system/<int:id>/army', methods=["GET"])
@login_required
@serialize
@json_description(file='descriptions/systems.json')
def get_system_army(id):
    system = System.get(id=id)
    return system.army
