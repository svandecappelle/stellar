# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.models.game.territory import Territory
from app.models.game.buildings import BuildingType


@app.route('/api/territory/<int:territory_id>', methods=['GET'])
@login_required
@serialize
def get_territory(territory_id):
    # TODO check building name before try to instanciate
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    return territory


@app.route('/api/territory/<int:territory_id>/<string:building>', methods=['POST'])
@login_required
@serialize
def build(territory_id, building):
    # TODO check building name before try to instanciate
    type = BuildingType.get_by_name(name=building)
    me = current_user.get()
    territory = Territory.get(id=territory_id, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    if not territory.can_be_increased(type):
        raise ValueError(f"Cannot increase {building} building level. Prerequisites not reached.")
    event = territory.increase(type)
    db.session.commit()
    return event
