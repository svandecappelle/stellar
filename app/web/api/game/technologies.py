# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.models.game.event import PositionalEvent, PositionalEventType
from app.models.game.territory import Territory

from app.models.game.technologies.technology import Technology, TechnologyType


@app.route('/api/technologies', methods=['GET'])
@login_required
@serialize
def get_my_technologies():
    return Technology.all(user=current_user.get())


@app.route('/api/technology/<string:name>/<int:territory>', methods=['POST'])
@login_required
@serialize
def increase_technology(name, territory):
    me = current_user.get()
    territory = Territory.get(id=territory, user=me)
    if not territory:
        raise ValueError("Territory does not owned by you")
    technology = Technology.get(user=me, type=TechnologyType.get_by_name(name))
    if technology.can_be_increased(territory=territory):
        event = technology.increase(territory=territory)
        db.session.commit()
        return event
    raise ValueError(f"Technology {name} can not be increased. Prerequisites not reached.")


@app.route('/api/technologies/events', methods=['GET'])
@login_required
@serialize
def get_pending_technologies():
    return PositionalEvent.all(user=current_user.get(), event_type=PositionalEventType.technology)
