# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, serialize
from app.application import login_required


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

