# -*- coding: utf-8 -*-
import json

from flask import jsonify, request, abort
from flask_login import current_user
from sqlalchemy.orm.exc import NoResultFound

from app.application import app, db, serialize
from app.application import login_required

from app.models.game.galaxy import Galaxy
from app.models.game.system import System
from app.models.role import RoleType
from app.web.api.exceptions import NotFoundError, ConflictError


@app.route('/api/galaxy/create', methods=['POST'])
@login_required
@serialize
def initialize_galaxy():
    if RoleType.admin in current_user.get().roles:
        # TODO raise not allowed
        raise ValueError("not allowed")

    name = request.json.get('name')
    nb_sectors = request.json.get('sectors')
    properties = request.json.get('properties')

    if not name:
        raise ValueError(400, 'name is required')
    if not nb_sectors:
        raise ValueError(400, 'sectors is required')
    if Galaxy.exists(session=db.session, name=name):
        raise ConflictError(message='Galaxy is already initialized')
    galaxy = Galaxy.create(session=db.session, name=name, sector_number=nb_sectors, properties=properties)
    db.session.commit()
    return galaxy

@app.route('/api/galaxy/batch_initialize', methods=['POST'])
@login_required
@serialize
def initialize_systems():
    #if RoleType.admin not in current_user.get().roles:
    #    # TODO raise not allowed
    #    raise ValueError("not allowed")
    systems = request.json.get('systems')
    galaxy_name = request.json.get('galaxy_name')
    if not systems:
        raise ValueError(400, 'systems is required')
    if not Galaxy.exists(session=db.session, name=galaxy_name):
        raise NotFoundError("Galaxy does not exists")
    galaxy = Galaxy.get(session=db.session, name=galaxy_name)
    for s in systems:
        position = s["position"]
        characteristics = s["characteristics"]
        System.create(
            galaxy=galaxy,
            position=f"{position['x']}_{position['y']}_{position['z']}",
            characteristics=characteristics
        )
    db.session.commit()


@app.route('/api/galaxies', methods=['GET'])
@serialize
def get_all_galaxies():
    return db.session.query(Galaxy).all()


@app.route('/api/galaxy/<string:name>', methods=['GET'])
@serialize
def get_galaxy_detail(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        raise NotFoundError(404, 'Galaxy does not exists')
    return galaxy


@app.route('/api/galaxy/<string:name>/systems', methods=['GET'])
@serialize
def get_galaxy_systems(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        raise NotFoundError(404, 'Galaxy does not exists')
    return {
        "galaxy_name": galaxy.name, 
        "systems": galaxy.systems,
        "properties": json.loads(galaxy.properties),
    }
