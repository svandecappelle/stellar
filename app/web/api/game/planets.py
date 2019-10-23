# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g

from app.application import app
from app.application import login_required


@app.route('/api/planet/{}', methods=['GET'])
@login_required
def get_planet_detail():
    return jsonify({})
