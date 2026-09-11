# -*- coding: utf-8 -*-

"""
Les lignes de commerce.

    GET    /api/trade            les lignes du joueur
    POST   /api/trade            en ouvrir une — consomme un cargo
    POST   /api/trade/<id>       declarer ce qui y circule
    DELETE /api/trade/<id>       la demonter

Un cargo fait le premier voyage et etablit la route ; apres quoi les ressources
coulent d'elles-memes. Le cargo est CONSOMME : il devient l'infrastructure de la
ligne, comme le vaisseau de colonisation devient la colonie.

Ce que les routes ne font pas : deplacer les ressources. C'est le tour de jeu du
territoire de depart qui les fait couler — voir `Territory._run_trade`. Une
route qui transporterait a la demande transformerait chaque clic en convoi, et
ce n'est pas ce qui a ete decide.
"""

from flask import request
from flask_login import current_user

from app.application import app, db, json_description, login_required, serialize
from app.models.audit import Action, record
from app.models.game.fleet import Fleet
from app.models.game.ship import ShipType
from app.models.game.territory import Territory
from app.models.game.trade import TradeLine
from app.web.api.exceptions import (
    BadRequestError, ConflictError, NotFoundError)


@app.route('/api/trade', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/trade.json')
def get_trade_lines():
    """
    Les lignes du joueur, ouvertes comme fermees.
    ---
    Les fermees sont gardees : elles disent qu'une route a existe, et a quel
    moment elle a cesse. Le client peut les filtrer, le serveur n'a pas a
    decider pour lui ce qui est encore interessant.
    """
    return {
        'lines': [line.serialize
                  for line in TradeLine.of(user=current_user.get(), open_only=False)],
        # Ce qui voyage, dit par le serveur. Le client dresse sa liste de flux
        # a partir de la : recopiee, elle offrirait l'energie — qui se produit
        # et se consomme sur place — et la route la refuserait ensuite. Meme
        # principe que `construction` sur la fiche territoire.
        'tradeable': sorted(r.name for r in Territory.TRADEABLE),
    }


@app.route('/api/trade', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/trade.json')
def open_trade_line():
    """
    Ouvre une ligne entre deux territoires du joueur.
    ---
    Le cargo doit etre en orbite du territoire d'ARRIVEE : c'est lui qui vient
    de faire le voyage, et c'est ce voyage qui etablit la route. Exiger qu'il
    soit au depart reviendrait a ouvrir une ligne sans que personne ne l'ait
    jamais parcourue.

    Le corps : `{"origin_id": 12, "destination_id": 34}`.
    """
    user = current_user.get()
    payload = request.get_json(silent=True) or {}

    origin = _own_territory(payload.get('origin_id'), user)
    destination = _own_territory(payload.get('destination_id'), user)

    if origin.id == destination.id:
        raise BadRequestError("A line needs two different worlds")

    if origin.galaxy_name != destination.galaxy_name:
        # Une ligne ne traverse pas les galaxies : les couloirs ne relient que
        # les etoiles d'une meme galaxie, et un cargo n'a aucun chemin a suivre.
        raise BadRequestError("Both worlds must be in the same galaxy")

    if TradeLine.between(origin=origin, destination=destination) is not None:
        raise ConflictError("These worlds are already linked")

    _consume_freighter(destination=destination, user=user)

    line = TradeLine(
        user_id=user.id, origin_id=origin.id, destination_id=destination.id)
    db.session.add(line)
    db.session.flush()

    record(Action.TRADE_OPEN, line_id=line.id,
           origin_id=origin.id, destination_id=destination.id)
    db.session.commit()
    return line


@app.route('/api/trade/<int:id>', methods=['POST', 'PUT'])
@login_required
@serialize
@json_description(file='descriptions/trade.json')
def set_trade_flows(id):
    """
    Declare ce qui circule sur une ligne, et dans quel sens.
    ---
    Le corps : `{"flows": [{"resource": "food", "rate": 280,
    "to_origin": false}]}`.

    La somme des debits n'est pas bornee ici : c'est le tour de jeu qui
    s'arrete au debit de la ligne, flux par flux et dans l'ordre declare. Le
    refuser a la declaration obligerait le joueur a recalculer son reseau
    chaque fois qu'un depot monte d'un niveau.
    """
    line = _own_line(id, current_user.get())
    payload = request.get_json(silent=True) or {}
    wanted = payload.get('flows')

    if not isinstance(wanted, list):
        raise BadRequestError("flows must be a list")

    clean = []
    for flow in wanted:
        if not isinstance(flow, dict):
            raise BadRequestError("each flow must be an object")

        name = flow.get('resource')
        if name not in {r.name for r in Territory.TRADEABLE}:
            raise BadRequestError(
                "%r does not travel on a trade line. Energy is produced and "
                "spent where it stands, and people travel by colony ship."
                % name)

        try:
            rate = float(flow.get('rate') or 0)
        except (TypeError, ValueError):
            raise BadRequestError("rate must be a number")
        if rate < 0:
            raise BadRequestError("rate cannot be negative")

        clean.append({
            'resource': name,
            'rate': rate,
            'to_origin': bool(flow.get('to_origin')),
        })

    line.flows = clean
    record(Action.TRADE_FLOWS, line_id=line.id, flows=clean)
    db.session.commit()
    return line


@app.route('/api/trade/<int:id>', methods=['DELETE'])
@login_required
@serialize
@json_description(file='descriptions/trade.json')
def close_trade_line(id):
    """
    Demonte une ligne.
    ---
    La ligne est gardee, fermee : elle dit qu'une route a existe. Le cargo qui
    l'avait ouverte ne revient pas — il s'etait consomme a l'ouverture.
    """
    line = _own_line(id, current_user.get())
    if not line.is_open:
        raise ConflictError("This line is already closed")

    line.close()
    record(Action.TRADE_CLOSE, line_id=line.id)
    db.session.commit()
    return line


# ── Outillage ───────────────────────────────────────────────────────────────

def _own_territory(territory_id, user):
    if not territory_id:
        raise BadRequestError("origin_id and destination_id are required")

    territory = Territory.get(id=territory_id)
    if territory is None:
        raise NotFoundError("Territory does not exist")
    if territory.user_id != user.id:
        # 404 et non 403 : repondre « interdit » confirmerait a qui essaie des
        # identifiants qu'un monde s'y trouve.
        raise NotFoundError("Territory does not exist")
    return territory


def _own_line(line_id, user):
    line = db.session.query(TradeLine).filter(TradeLine.id == line_id).first()
    if line is None or line.user_id != user.id:
        raise NotFoundError("Trade line does not exist")
    return line


def _consume_freighter(destination, user):
    """Retire un cargo de l'orbite du territoire d'arrivee."""
    for fleet in Fleet.in_orbit_of(territory=destination, user=user):
        for ship in fleet.ships:
            if ship.type == ShipType.Freighter and ship.count > 0:
                ship.decrement(1)
                return

    raise BadRequestError(
        "No Freighter in orbit of the destination. A line is opened by a "
        "convoy that has made the trip.")
