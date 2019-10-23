# -*- coding: utf-8 -*-

import werkzeug.exceptions as ex
from flask import jsonify, request, session, g, abort
from flask_sqlalchemy_session import flask_scoped_session

from app.application import app, db
from app.application import login_required

from app.models.game.galaxy import Galaxy


@app.route('/api/galaxy/create', methods=['POST'])
@login_required
def initialize_galaxy():
    name = request.json.get('name')
    if not name:
        abort(400, 'Name is required')
    if Galaxy.get(session=db.session):
        abort(400, 'Galaxy is already initialized')
    galaxy = Galaxy.create(session=db.session, name=name)
    db.session.commit()
    return jsonify(galaxy.serialize)


# @serialize
@app.route('/api/galaxy', methods=['get'])
@login_required
def get_galaxy_detail():
    return jsonify(Galaxy.get(session=db.session).serialize)
