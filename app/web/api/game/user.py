# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description

from app.models.audit import Action, record
from app.models.game.community.faction import Faction
from app.models.game.fleet import Fleet
from app.models.game.planet import PlanetArchetype, SETTLEMENT_STATION
from app.models.game.ship import ShipType
from app.models.game.territory import Territory
from app.web.api.exceptions import BadRequestError, ConflictError, NotFoundError

@app.route('/api/events', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/events.json')
def get_my_events():
    for event_type, events in current_user.get().events.items():
        for event in events:
            event.update_event()

    return current_user.get().events

@app.route('/api/territory/<int:id>', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def claim_territory(id):
    """
    Attribue un monde au joueur : premier monde, colonie, ou plateforme.
    ---
    Un seul chemin pour les trois, et ce qui les distingue est ce que le joueur
    possede deja dans la galaxie :

      · **Aucun monde** — c'est son installation. Aucune coque n'est demandee,
        et le monde doit etre tellurique : c'est le seul archetype qui produise
        a la fois du fer, du carbone et du silicium, donc le seul sur lequel une
        colonie tient debout sans rien importer. Ce monde devient sa capitale.

      · **Un monde solide, deja installe** — il faut un vaisseau de colonisation
        en orbite. Il est consomme, et ses colons peuplent le nouveau monde.

      · **Un corps sans surface** — geante gazeuse, asteroide, anomalie : il
        faut une plateforme d'extraction en orbite. Elle est consommee, et le
        territoire nait orbital : pas de population, quatre modules.

    L'orbite est le declencheur des deux derniers cas, et elle est declaree —
    `Fleet.orbiting_territory_id` — non deduite d'une distance que seul le
    client connaitrait.
    """
    user = current_user.get()

    territory = Territory.get(id=id)
    if not territory:
        raise NotFoundError("Territory does not exist")

    if territory.user_id:
        raise ConflictError("Territory already has an owner")

    # Un monde de depart par galaxie, pas un pour toute la partie : un joueur
    # installe ailleurs arrive ici sans rien posseder dans celle-ci.
    galaxy_name = territory.galaxy_name
    settled = any(t.galaxy_name == galaxy_name for t in user.territories)

    if not settled:
        if territory.planet_archetype != PlanetArchetype.telluric:
            raise BadRequestError(
                "A starting world must be telluric, not %s"
                % territory.planet_archetype.name)
        hull = None
    else:
        refusal = territory.claim_refusal(user=user)
        if refusal:
            raise BadRequestError(refusal)
        hull = _consume_hull(territory=territory, user=user)

    territory.claim(user=user)

    if hull is not None and territory.orbital is False:
        # Les colons du vaisseau peuplent le monde. `assign` a pose la
        # population par defaut de la planete ; c'est celle du vaisseau qui
        # compte, sans quoi coloniser reviendrait a fabriquer des gens.
        territory.population = COLONISTS_PER_SHIP

    record(Action.TERRITORY_CLAIM, territory_id=territory.id,
           galaxy=galaxy_name, system_id=territory.system_id,
           orbital=bool(territory.orbital), first=not settled)
    db.session.commit()

    # Celui qu'on vient d'attribuer, pas le premier de la liste : le joueur
    # peut deja tenir un monde dans une autre galaxie.
    return territory


#: Colons debarques par vaisseau de colonisation. C'est aussi ce que la coque
#: coute en population au monde qui l'arme — voir `ShipType.ColonyShip` : les
#: gens montent a bord, ils ne se multiplient pas en chemin.
COLONISTS_PER_SHIP = 40


def _consume_hull(territory, user):
    """
    Trouve la coque exigee en orbite et en retire une.

    :return: le `ShipType` consomme.
    :raises BadRequestError: si rien en orbite ne porte ce qu'il faut.
    """
    needed = (ShipType.ExtractionPlatform
              if territory.settlement_kind() == SETTLEMENT_STATION
              else ShipType.ColonyShip)

    for fleet in Fleet.in_orbit_of(territory=territory, user=user):
        for ship in fleet.ships:
            if ship.type == needed and ship.count > 0:
                # Consommee : c'est la seule regle neuve du modele de flotte, et
                # elle vaut pour les deux coques. Un vaisseau de colonisation
                # qui survivrait a sa colonie en fonderait une par systeme.
                ship.decrement(1)
                return needed

    raise BadRequestError(
        "No %s in orbit of this world. Send one there first." % needed.name)

@app.route('/api/territories', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_territories():
    """
    Tous les territoires du joueur, galaxies confondues.
    ---
    Pour travailler dans une galaxie donnee, prefer
    /api/galaxy/<name>/territories : un territoire est toujours rattache a une
    galaxie via son systeme. Cette route reste pour la seule question qui ne se
    pose pas dans une galaxie : ou le joueur possede-t-il quelque chose ?
    """
    return {
        'territories': current_user.get().territories
    }

@app.route('/api/faction/<int:faction_id>', methods=['PUT'])
@login_required
@serialize
@json_description(file='descriptions/factions.json')
def affect_faction_to_user(faction_id):
    """
    Affect a faction to a user
    """
    try:
        faction = Faction.get(id=faction_id)
    except:
        raise BadRequestError("Faction does not exist")
    user = current_user.get()
    if user.faction:
        raise ConflictError("User already has a faction")

    user.affect_faction(faction=faction)

    # Le `commit` manquait. En test, la session survit a la requete et la
    # faction paraissait posee ; en production, la session `scoped` est rendue
    # au bout de chaque requete et ce qui n'a pas ete valide part avec elle —
    # le joueur choisissait donc sa faction sans qu'elle soit jamais
    # enregistree. Revele par l'annulation que fait le journal d'audit sur un
    # refus, qui rend la session au propre entre deux appels comme le ferait la
    # production.
    db.session.commit()
    return None
