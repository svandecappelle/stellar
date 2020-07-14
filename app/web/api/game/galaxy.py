# -*- coding: utf-8 -*-

from flask import jsonify, request, abort
from sqlalchemy.orm.exc import NoResultFound

from app.application import app, db, serialize
from app.application import login_required

from app.models.game.galaxy import Galaxy
from app.web.api.exceptions import NotFoundError, ConflictError


@app.route('/api/galaxy/create', methods=['POST'])
@login_required
@serialize
def initialize_galaxy():
    name = request.json.get('name')
    if not name:
        raise ValueError(400, 'Name is required')
    if Galaxy.exists(session=db.session, name=name):
        raise ConflictError(message='Galaxy is already initialized')
    galaxy = Galaxy.create(session=db.session, name=name)
    db.session.commit()
    return galaxy


@app.route('/api/galaxy/:name', methods=['get'])
@serialize
def get_galaxy_detail(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        raise NotFoundError(404, 'Galaxy does not exists')
    return galaxy
