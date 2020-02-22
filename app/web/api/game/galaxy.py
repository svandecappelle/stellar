# -*- coding: utf-8 -*-

from flask import jsonify, request, abort
from sqlalchemy.orm.exc import NoResultFound

from app.application import app, db, serialize
from app.application import login_required

from app.models.game.galaxy import Galaxy


@app.route('/api/galaxy/create', methods=['POST'])
@login_required
@serialize
def initialize_galaxy():
    name = request.json.get('name')
    if not name:
        abort(400, 'Name is required')
    if Galaxy.exists(session=db.session, name=name):
        abort(400, 'Galaxy is already initialized')
    galaxy = Galaxy.create(session=db.session, name=name)
    db.session.commit()
    return galaxy


@app.route('/api/galaxy/:name', methods=['get'])
@serialize
def get_galaxy_detail(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        abort(404, 'Galaxy does not exists')
    return galaxy
