# -*- coding: utf-8 -*-

from app.application import app


@app.route('/api/mon/ping', methods=['GET'])
def ping():
    """
    Monitoring on api arsenal
    """
    return "Pong", 200
