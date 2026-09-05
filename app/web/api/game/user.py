# -*- coding: utf-8 -*-

from flask_login import current_user

from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description

from app.models.game.community.faction import Faction
from app.models.game.planet import PlanetArchetype
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
def affect_first_territory(id):
    """
    Attribue au joueur son monde de depart.
    ---
    Le premier monde est toujours tellurique : c'est le seul archetype qui
    produit a la fois du fer, du carbone et du silicium, donc le seul sur
    lequel une colonie tient debout sans rien importer.
    """
    user = current_user.get()

    territory = Territory.get(id=id)
    if not territory:
        raise NotFoundError("Territory does not exist")

    # Un monde de depart par galaxie, pas un pour toute la partie : un joueur
    # installe ailleurs arrive ici sans rien posseder dans celle-ci, et le
    # refus global lui interdisait de s'installer une seconde fois.
    galaxy_name = territory.galaxy_name
    if any(t.galaxy_name == galaxy_name for t in user.territories):
        raise ConflictError("User already has a territory in this galaxy")

    if territory.user_id:
        raise ConflictError("Territory already has an owner")
    if territory.planet_archetype != PlanetArchetype.telluric:
        raise BadRequestError(
            "A starting world must be telluric, not %s" % territory.planet_archetype.name
        )

    territory.assign(user=user)
    db.session.commit()
    # Celui qu'on vient d'attribuer, pas le premier de la liste : le joueur
    # peut deja tenir un monde dans une autre galaxie.
    return territory

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
    return None
