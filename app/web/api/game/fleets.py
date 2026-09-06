# -*- coding: utf-8 -*-

"""
Routes des flottes.

Une flotte est ce qui existe dans l'espace d'un systeme : elle porte les
vaisseaux, une position en coordonnees Unity et, quand elle est amarree, la
planete dont elle tient l'orbite.

Le serveur ne fait rien de la position : il l'enregistre et la rend. La
geometrie du systeme vit chez le client, qui seul sait ou passe une orbite. De
meme l'orbite est declaree, jamais deduite d'une distance — c'est pourtant elle
qui decide a quelle flotte revient un vaisseau qui sort de chantier, voir
`Fleet.receive_construction`.
"""

from flask import request
from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description
from app.models.game.fleet import Fleet
from app.models.game.system import System
from app.models.game.territory import Territory
from app.web.api.exceptions import BadRequestError, ConflictError, NotFoundError
from logger import logger


def _own_fleet(fleet_id):
    """
    La flotte du joueur, ou un 404.
    ---
    Restreinte a son proprietaire des la requete : une flotte qui n'est pas la
    sienne doit rester introuvable, et non refusee — repondre 403 apprendrait
    au joueur qu'elle existe.
    """
    fleet = Fleet.get(id=fleet_id, user=current_user.get())
    if fleet is None:
        raise NotFoundError("Fleet does not exist")
    return fleet


def _position(payload):
    """
    Lit un point {x, y, z}, et refuse ce qui n'en est pas un.
    ---
    Rend None quand le client n'en fournit pas : la console web manoeuvre les
    flottes sans jamais savoir ou elles sont a l'ecran, et laisser la position
    inchangee est la bonne reponse pour elle.
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise BadRequestError("position must be an object with x, y and z")
    point = {}
    for axis in ('x', 'y', 'z'):
        if axis not in payload:
            continue
        try:
            point[axis] = float(payload[axis])
        except (TypeError, ValueError):
            raise BadRequestError("position.%s must be a number" % axis)
    return point or None


def _orbit_target(territory_id, system_id):
    """
    Verifie qu'une orbite demandee est bien une planete de ce systeme.
    ---
    Sans ce controle une flotte pourrait declarer tenir l'orbite d'un monde a
    l'autre bout de la galaxie, et `Fleet.receive_construction` livrerait les
    vaisseaux d'un chantier a une flotte qui n'a jamais ete la.
    """
    # Zero vaut absence d'orbite au meme titre que null : JsonUtility, cote
    # Unity, ne sait pas ecrire un entier nul et envoie zero pour dire « aucune
    # planete ». Aucun territoire ne porte l'identifiant zero, la confusion est
    # donc sans consequence.
    if not territory_id:
        return None
    territory = Territory.get(id=territory_id)
    if territory is None:
        raise NotFoundError("Territory does not exist")
    if territory.system_id != system_id:
        raise BadRequestError("Territory is not in the same system as the fleet")
    return territory.id


@app.route('/api/system/<int:id>/fleets', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def get_system_fleets(id):
    """Les flottes du joueur dans ce systeme, position et composition."""
    system = System.get(id=id)
    return {
        'id': system.id,
        'fleets': Fleet.in_system(system_id=system.id, user=current_user.get()),
    }


@app.route('/api/fleet/<int:id>', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def get_fleet(id):
    return _own_fleet(id)


@app.route('/api/system/<int:id>/fleet', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def create_fleet(id):
    """
    Cree une flotte vide dans un systeme.
    ---
    Le joueur en a besoin pour scinder ce qu'il possede, ou pour preparer une
    destination aux sorties de chantier. Le serveur en cree aussi de lui-meme
    a la livraison des vaisseaux ; les deux passent par le meme modele.
    """
    system = System.get(id=id)
    payload = request.json or {}
    fleet = Fleet.create(
        system_id=system.id,
        user=current_user.get(),
        name=payload.get('name'),
        position=_position(payload.get('position')),
        orbiting_territory_id=_orbit_target(
            payload.get('orbiting_territory_id'), system.id),
    )
    db.session.commit()
    return fleet


@app.route('/api/fleet/<int:id>', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def update_fleet(id):
    """
    Met a jour une flotte : nom, position, orbite.
    ---
    Les trois champs sont facultatifs et independants. Un champ absent laisse
    la valeur en place, ce qui permet au client de ne pousser que ce qu'il sait
    — la console web n'a pas de position a donner, Unity si.
    """
    fleet = _own_fleet(id)
    payload = request.json or {}

    if 'name' in payload:
        name = (payload.get('name') or '').strip()
        if not name:
            raise BadRequestError("name cannot be empty")
        fleet.name = name

    fleet.move_to(_position(payload.get('position')))

    if 'orbiting_territory_id' in payload:
        fleet.set_orbit(_orbit_target(
            payload.get('orbiting_territory_id'), fleet.system_id))

    db.session.commit()
    return fleet


@app.route('/api/fleet/<int:id>/position', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def move_fleet(id):
    """
    Pose la flotte a une position Unity.
    ---
    Le chemin frequent : Unity l'appelle a la fin de chaque manoeuvre pour que
    la flotte se retrouve au meme endroit a la prochaine entree dans le
    systeme. Rien n'est valide au-dela des trois nombres : le serveur ne
    connait pas la geometrie du systeme et n'a donc aucune idee de ce qu'est
    une position plausible.
    """
    fleet = _own_fleet(id)
    position = _position(request.json)
    if position is None:
        raise BadRequestError("position is required")
    fleet.move_to(position)
    db.session.commit()
    return fleet


@app.route('/api/fleet/<int:id>/orbit', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def orbit_fleet(id):
    """
    Amarre la flotte a l'orbite d'une planete, ou l'en detache.
    ---
    `{"territory_id": null}` la detache, `0` egalement — c'est ce qu'envoie
    Unity, dont le serialiseur ne sait pas ecrire un entier nul. C'est cette declaration, et elle
    seule, qui dit au serveur ce qui se trouve en orbite quand un chantier
    livre : une flotte qui part sans se detacher continuera de recevoir les
    vaisseaux assembles derriere elle.
    """
    fleet = _own_fleet(id)
    payload = request.json or {}
    if 'territory_id' not in payload:
        raise BadRequestError("territory_id is required, use null to leave orbit")
    fleet.set_orbit(_orbit_target(payload.get('territory_id'), fleet.system_id))
    db.session.commit()
    return fleet


@app.route('/api/fleet/<int:id>', methods=['DELETE'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def delete_fleet(id):
    """
    Dissout une flotte vide.
    ---
    Une flotte qui porte encore des vaisseaux n'est pas dissoute : ce serait
    les detruire sans le dire. Au joueur de les transferer d'abord.
    """
    fleet = _own_fleet(id)
    if not fleet.is_empty:
        raise ConflictError("Fleet still holds ships")
    logger.info(f"Fleet {fleet.id} disbanded", infos=dict(fleet_id=fleet.id))
    db.session.delete(fleet)
    db.session.commit()
    return None


@app.route('/api/fleet/<int:id>/transfer', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/fleets.json')
def transfer_ships(id):
    """
    Deplace des vaisseaux d'une flotte a une autre.
    ---
    C'est le geste que reclame la regle de sortie de chantier : quand plusieurs
    flottes tiennent l'orbite, le serveur en cree une neuve plutot que de
    choisir, et c'est ici que le joueur recolle ce qu'il voulait ensemble.

    Les deux flottes doivent etre a lui et dans le meme systeme : un transfert
    n'est pas un voyage.
    """
    source = _own_fleet(id)
    payload = request.json or {}

    target = Fleet.get(id=payload.get('to'), user=current_user.get())
    if target is None:
        raise NotFoundError("Target fleet does not exist")
    if target.id == source.id:
        raise BadRequestError("Source and target fleets are the same")
    if target.system_id != source.system_id:
        raise BadRequestError("Both fleets must be in the same system")

    items = payload.get('items')
    if not items:
        raise BadRequestError("items is required")

    for item in items:
        ship = next((s for s in source.ships if s.type.name == item.get('type')), None)
        if ship is None:
            raise BadRequestError("Fleet holds no %s" % item.get('type'))
        quantity = int(item.get('quantity', 0))
        if quantity <= 0:
            raise BadRequestError("quantity must be positive")
        if quantity > ship.count:
            raise BadRequestError(
                "Fleet holds %d %s, cannot transfer %d" % (ship.count, ship.type.name, quantity))
        ship.decrement(count=quantity)
        target.add_ships(ship_type=ship.type, amount=quantity)

    db.session.commit()
    return [source, target]
