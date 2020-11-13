# -*- coding: utf-8 -*-

from flask import jsonify, request, abort
from sqlalchemy.orm.exc import NoResultFound

from app.application import app, db, serialize
from app.application import login_required
from app.models.game.community.faction import Faction

from app.models.game.galaxy import Galaxy
from app.web.api.exceptions import NotFoundError, ConflictError


@app.route('/api/galaxy/factions', methods=['POST'])
@login_required
@serialize
def initialize_factions():
    Faction.initialize(session=db.session)
    db.session.commit()
    return Faction.all(session=db.session)
