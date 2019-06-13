# -*- coding: utf-8 -*-

from app.application import APP as app


@app.route('/api/mon/ping', methods=['GET'])
def ping():
    """
    Monitoring on api arsenal
    """
    return "Pong", 200
