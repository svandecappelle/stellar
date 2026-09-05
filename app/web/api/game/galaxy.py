# -*- coding: utf-8 -*-
import json
import random

from flask import jsonify, request, abort
from flask_login import current_user
from sqlalchemy.orm.exc import NoResultFound

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description

from app.models.game.galaxy import Galaxy
from app.models.game.settings import DEFAULTS, PARAMETERS, GalaxySettings
from app.models.game.system import System
from app.models.game.territory import Territory
from app.models.role import Role, RoleType
from app.models.user import User
from app.web.api.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)

from logger import get_logger

@app.route('/api/galaxy/create', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/galaxy.json')
def initialize_galaxy():
    """
    Cree une galaxie, et en fait le createur moderateur.
    ---
    Ouvrir une partie, c'est en repondre : celui qui la cree recoit le role de
    moderateur sur elle, et lui seul — avec les administrateurs — pourra en
    regler le rythme. Voir /api/galaxy/<name>/settings.

    Le garde qui se trouvait ici comparait un RoleType a une liste d'objets Role
    et ne pouvait donc jamais etre vrai : il ne refusait rien. Il disait de plus
    l'inverse de son intention — il aurait interdit la creation aux seuls
    administrateurs. Retire plutot que corrige : le client cree une galaxie a
    chaque nouvelle partie, c'est le geste normal d'un joueur.
    """
    user = current_user.get()

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

    if not user.has_role(RoleType.moderator, scope=name):
        user.add_role(RoleType.moderator, scope=name)

    db.session.commit()
    return galaxy

@app.route('/api/galaxy/batch_initialize', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/galaxy.json')
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
            characteristics=characteristics,
            create_territories=False,
        )
    db.session.commit()


@app.route('/api/galaxies', methods=['GET'])
@serialize
@json_description(file='descriptions/galaxy.json')
def get_all_galaxies():
    return db.session.query(Galaxy).all()


@app.route('/api/galaxy/<string:name>', methods=['GET'])
@serialize
@json_description(file='descriptions/galaxy.json')
def get_galaxy_detail(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        get_logger().warn(f"Galaxy {name} does not exists")
        raise NotFoundError('Galaxy does not exists')
    return galaxy


@app.route('/api/galaxy/<string:name>/territories', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_galaxy_territories(name):
    """
    Territoires du joueur dans cette galaxie.
    ---
    Un territoire appartient a un systeme, qui appartient a une galaxie : c'est
    la portee naturelle de la liste. Remplace /api/territories, qui renvoie les
    territoires de toutes les galaxies confondues.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    territories = [t for t in current_user.get().territories if t.galaxy_name == name]
    return {
        'galaxy_name': name,
        'territories': territories,
    }


@app.route('/api/galaxy/<string:name>/settings', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/galaxy.json')
def get_galaxy_settings(name):
    """
    Reglages de jeu de la galaxie.
    ---
    Lisible par tout joueur : ces valeurs decident des durees et des rendements
    qu'il a sous les yeux, il a le droit de savoir a quel rythme il joue. Seul
    un moderateur de cette galaxie peut les changer, ce que dit `can_edit`.

    La description des parametres est servie avec eux : la console construit son
    formulaire a partir de la, plutot que de redire ici ce que le serveur sait
    deja — bornes comprises.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    user = current_user.get()
    row = GalaxySettings.row_for(name)

    return {
        'galaxy_name': name,
        'settings': GalaxySettings.effective_for(name),
        'defaults': dict(DEFAULTS),
        'overrides': dict(row.overrides) if row and row.overrides else {},
        'parameters': [parameter.serialize for parameter in PARAMETERS],
        'can_edit': user.moderates(name),
        'moderators': moderators_of(name),
        'updated_at': row.updated_at.isoformat() if row and row.updated_at else None,
    }


@app.route('/api/galaxy/<string:name>/settings', methods=['POST', 'PUT'])
@login_required
@serialize
@json_description(file='descriptions/galaxy.json')
def update_galaxy_settings(name):
    """
    Change les reglages de jeu de la galaxie.
    ---
    Reserve aux moderateurs de cette galaxie et aux administrateurs. Le corps
    accepte soit {"settings": {...}}, soit directement les cles : la console
    envoie le formulaire entier, un appel a la main n'en change souvent qu'une.

    Les cles absentes ne sont pas touchees, une valeur hors bornes est refusee
    avec ses bornes, et une valeur egale au defaut efface le reglage plutot que
    de l'enregistrer.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    user = current_user.get()
    if not user.moderates(name):
        raise PermissionDeniedError(
            "Only a moderator of %s can change its settings" % name)

    payload = request.json or {}
    wanted = payload.get('settings', payload)

    try:
        settings = GalaxySettings.write(galaxy_name=name, wanted=wanted)
    except ValueError as error:
        raise BadRequestError(message=str(error))

    logger = get_logger()
    logger.info(
        "Galaxy settings updated",
        infos=dict(galaxy=name, user_id=user.id, settings=settings),
    )

    return {
        'galaxy_name': name,
        'settings': settings,
        'defaults': dict(DEFAULTS),
        'parameters': [parameter.serialize for parameter in PARAMETERS],
        'can_edit': True,
        'moderators': moderators_of(name),
    }


def moderators_of(galaxy_name):
    """
    Qui modere cette galaxie, par leur nom.
    ---
    Les administrateurs n'y figurent pas : leur portee est '*', ils moderent
    tout, et les lister ici ferait passer un droit general pour un droit sur
    cette partie.
    """
    rows = (
        db.session.query(User.username)
        .join(Role, Role.user_id == User.id)
        .filter(Role.role_type == RoleType.moderator.value)
        .filter(Role.scope == galaxy_name)
        .filter(Role.deleted_at == None)  # noqa: E711 - SQL, pas Python
        .distinct()
        .all()
    )
    return sorted(row[0] for row in rows)


@app.route('/api/galaxy/<string:name>/free-system', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/systems.json')
def get_free_system(name):
    """
    Un systeme ou personne ne s'est encore installe.
    ---
    Sert a poser le monde de depart d'un nouveau joueur : on tire au hasard
    parmi les systemes dont aucun territoire n'appartient a quelqu'un. Un
    systeme encore vierge de territoires en fait partie, c'est meme le cas le
    plus courant sur une galaxie neuve — le client les creera en y entrant.

    Rien n'est reserve ici. Deux joueurs servis en meme temps peuvent recevoir
    le meme systeme ; c'est l'attribution du territoire qui tranche, en
    refusant le second avec un conflit.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    # Les systemes occupes de CETTE galaxie : parcourir les territoires de
    # toutes les autres ne changeait pas le resultat, mais faisait payer le
    # balayage complet de la table a chaque nouveau joueur.
    taken = [
        row[0]
        for row in db.session.query(Territory.system_id)
        .join(System, System.id == Territory.system_id)
        .filter(System.galaxy_name == name)
        .filter(Territory.user_id != None)  # noqa: E711 - SQL, pas Python
        .distinct()
        .all()
    ]

    query = db.session.query(System).filter(System.galaxy_name == name)
    if taken:
        query = query.filter(~System.id.in_(taken))

    free = query.all()
    if not free:
        # Une galaxie sans systeme enregistre tombe ici : elle existe en base
        # sans avoir jamais ete generee, et il n'y a nulle part ou s'installer.
        raise NotFoundError('No unclaimed system left in this galaxy')

    return random.choice(free)


@app.route('/api/galaxy/<string:name>/systems', methods=['GET'])
@serialize
@json_description(file='descriptions/galaxy.json')
def get_galaxy_systems(name):
    try:
        galaxy = Galaxy.get(session=db.session, name=name)
    except NoResultFound:
        raise NotFoundError('Galaxy does not exists')
    only_mine = request.args.get('mine', "false")
    if only_mine.lower() in ['true']:
        systems = System.all(galaxy=galaxy, user=current_user.get())
    else:
        systems = galaxy.systems
    return {
        "galaxy_name": galaxy.name, 
        "systems": systems,
        "properties": json.loads(galaxy.properties),
    }
