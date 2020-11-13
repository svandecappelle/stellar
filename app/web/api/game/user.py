# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, serialize
from app.application import login_required

from app.models.game.community.faction import Faction
from app.web.api.exceptions import BadRequestError, ConflictError

@app.route('/api/events', methods=['GET'])
@login_required
@serialize
def get_my_events():
    for event_type, events in current_user.get().events.items():
        for event in events:
            event.update_event()

    return current_user.get().events


@app.route('/api/territories', methods=['GET'])
@login_required
@serialize
def get_territories():
    return current_user.get().territories

@app.route('/api/faction/<int:faction_id>', methods=['PUT'])
@login_required
@serialize
def affect_faction_to_user(faction_id):
    """
    Affect a faction to a user
    """
    try:
        faction = Faction.get(id=faction_id)
    except:
        raise BadRequestError("Faction does not exist")
    user = current_user.get()
    if user.faction:
        raise ConflictError("User already has a faction")
    user.affect_faction(faction=faction)
    return None
