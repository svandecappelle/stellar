# -*- coding: utf-8 -*-

from app.application import app, json_description


@app.route('/api/mon/ping', methods=['GET'])
@json_description(file='descriptions/monitoring.json')
def ping():
    """
    Monitoring on api arsenal
    """
    return "Pong", 200
