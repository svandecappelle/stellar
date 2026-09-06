# -*- coding: utf-8 -*-

from flask import request
from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description
from app.models.game.territory import Territory
from app.models.game.buildings import BuildingType
from app.models.game.event import PositionalEventType
from logger import logger


@app.route('/api/territory/<int:territory_id>', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_territory(territory_id):
    # TODO check building name before try to instanciate
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    territory.update_view()
    return territory

@app.route('/api/territory/<int:territory_id>/update', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def update_territory_view(territory_id):
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    territory.update_view()
    return territory

# `GET /api/territory/<id>/ships` a ete retire : un vaisseau assemble quitte la
# planete pour l'espace du systeme, ou il appartient a une flotte. Ce que le
# joueur possede se lit desormais par `GET /api/system/<id>/fleets`, et ce qui
# tient l'orbite d'une planete se reconnait au champ `orbiting_territory_id` de
# chaque flotte.


@app.route('/api/territory/<int:territory_id>/defenses', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_territory_defenses(territory_id):
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    return territory.defenses


@app.route('/api/territory/<int:territory_id>/events', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_territory_events(territory_id):
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    return territory.territory_events


@app.route('/api/territory/<int:territory_id>/<string:building>', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def build(territory_id, building):
    # TODO check building name before try to instanciate
    type = BuildingType.get_by_name(name=building)
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    if not territory.can_be_increased(type):
        logger.info(f"Cannot increase {type} building level. Prerequisites not reached.")
        raise ValueError(f"Cannot increase {building} building level. Prerequisites not reached.")
    event = territory.increase(type)
    db.session.commit()
    return event


@app.route('/api/territory/<int:territory_id>/defense', methods=['POST'])
@app.route('/api/territory/<int:territory_id>/ship', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def build_defense_or_ship(territory_id):
    """
    Lance un chantier de vaisseaux ou de defenses.
    ---
    `spawn` est le point d'apparition Unity de la flotte que le serveur creera
    si aucune ne tient l'orbite a la livraison. Le client seul connait la
    geometrie du systeme, donc l'endroit ou une flotte doit apparaitre au-dessus
    de cette planete ; la console web, qui n'en a pas, l'omet.
    """
    type = PositionalEventType(request.path.split('/')[-1:][0])
    payload = request.json or {}
    items = payload.get('items')
    spawn = payload.get('spawn') if type == PositionalEventType.ship else None
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    events = []
    for item in items:
        events.append(territory.build(type, item, spawn=spawn))
    db.session.commit()
    return events
