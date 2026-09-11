# -*- coding: utf-8 -*-

"""
L'API de la recherche.

Deux lectures et deux ecritures, et la separation entre elles est le point
important : `/api/technologies/tree` publie la FORME de l'arbre — couts, durees,
prerequis, effets — et ne depend d'aucun joueur ; `/api/technologies` publie
l'ETAT d'un joueur dans cet arbre. La premiere se met en cache une fois pour
toutes par les deux clients, la seconde se relit a chaque geste.

Aucune route ne prend de territoire. La recherche appartient au joueur, toutes
galaxies confondues, et se paie sur l'ensemble de ses mondes : lui faire
designer une planete revenait a plafonner son empire au stock du monde qu'il
avait sous les yeux.
"""

from flask import jsonify, request
from flask_login import current_user

from app.models.audit import Action, record
from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import TechnologyType, tree


@app.route('/api/technologies/tree', methods=['GET'])
@login_required
@json_description(file='descriptions/technologies.json')
def get_technology_tree():
    """
    Le catalogue : branches, paliers, noeuds, effets.
    ---
    Statique. Rien ici ne depend du joueur connecte, et c'est voulu — les deux
    clients dessinent l'arbre entier, y compris ce qu'ils n'ont pas encore
    atteint, et ne detiennent aucune copie des regles.
    """
    return jsonify(tree())


@app.route('/api/technologies', methods=['GET'])
@login_required
@json_description(file='descriptions/technologies.json')
def get_my_technologies():
    """
    L'etat du joueur : niveaux, recherches en cours, reserve, emplacements.
    ---
    Un objet et non plus une liste nue. La liste ne pouvait pas porter la
    reserve de Donnees ni le nombre d'emplacements ouverts, que le client doit
    pourtant afficher a cote des noeuds — il aurait fallu une seconde route
    pour ce qui se lit d'un seul coup d'oeil.
    """
    me = current_user.get()

    # Les lignes manquantes sont posees avant la lecture. Un compte cree sans
    # territoire puis installe plus tard n'en avait aucune, et l'arbre lui
    # apparaissait entier mais sans etat : chaque noeud s'affichait, aucun ne
    # s'ouvrait. C'est aussi ce qui rattrape un arbre agrandi dont la migration
    # n'a pas encore tourne.
    Technology.ensure(user=me)

    # `modifiers` encaisse au passage les recherches arrivees a terme : ce qui
    # est fini doit apparaitre fini, et compter dans les couts annonces juste
    # en dessous.
    modifiers = me.modifiers
    technologies = sorted(
        Technology.all(user=me),
        key=lambda t: (list(TechnologyType).index(t.type)))

    levels = Technology.levels(user=me)
    branch_totals = Technology.branch_levels(user=me)
    pending = Technology.pending(user=me)
    ordered = {e.extra_args.get('type'): e.extra_args for e in pending}

    db.session.commit()

    return jsonify({
        'research': round(float(me.research or 0.0), 2),
        'research_gain': _hourly_research(me),
        'slots': Technology.slots(user=me, modifiers=modifiers),
        'used_slots': len(pending),
        'branches': {branch.name: total for branch, total in branch_totals.items()},
        'pending': [event.serialize for event in pending],
        'modifiers': modifiers.serialize,
        'technologies': [
            technology.serialize_for(
                modifiers=modifiers,
                levels=levels,
                branch_totals=branch_totals,
                pending=ordered,
            )
            for technology in technologies
        ],
    })


@app.route('/api/technology/<string:name>', methods=['POST'])
# L'ancienne forme, avec un territoire dans le chemin. Conservee pour que les
# clients deja livres ne tombent pas sur un 404 : le territoire est ignore, la
# depense se fait sur l'empire. A retirer quand les deux clients seront a jour.
@app.route('/api/technology/<string:name>/<int:territory>', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/technologies.json')
def increase_technology(name, territory=None):
    """
    Lancer la recherche du niveau suivant.
    ---
    Le corps peut porter `{"choice": "..."}` : obligatoire sur une doctrine,
    refuse partout ailleurs.
    """
    me = current_user.get()
    tech_type = TechnologyType.get_by_name(name)
    if tech_type is None:
        raise ValueError("Technologie inconnue : %s." % name)

    payload = request.get_json(silent=True) or {}
    Technology.ensure(user=me)
    technology = Technology.get(user=me, type=tech_type)

    event = technology.increase(choice=payload.get('choice'))
    record(Action.RESEARCH_START, technology=name, choice=payload.get('choice'))
    # Le niveau n'a pas bouge, mais la reserve et les stocks si : l'ensemble
    # memorise ne vaut plus rien pour la suite de la requete.
    me.forget_modifiers()
    db.session.commit()
    return event


@app.route('/api/technology/queue/<int:event_id>', methods=['DELETE'])
@login_required
@serialize
@json_description(file='descriptions/technologies.json')
def cancel_technology(event_id):
    """
    Annuler une recherche en cours. La moitie de la depense revient la ou elle
    a ete prise ; la progression du niveau est perdue.
    """
    me = current_user.get()
    event = Technology.cancel(user=me, event_id=event_id)
    record(Action.RESEARCH_CANCEL, event_id=event_id)
    me.forget_modifiers()
    db.session.commit()
    return event


@app.route('/api/technologies/events', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/technologies.json')
def get_pending_technologies():
    """
    Les recherches en cours, seules.
    ---
    Conservee parce que les clients l'interrogent pour rafraichir un compte a
    rebours sans relire l'arbre entier.
    """
    me = current_user.get()
    Technology.catch_up(user=me)
    pending = Technology.pending(user=me)
    db.session.commit()
    return pending


def _hourly_research(user):
    """
    Donnees produites par heure, tous mondes confondus.
    ---
    C'est ce que le client met en face de la reserve : sans ce chiffre, une
    duree de recherche ne dit pas au joueur s'il aura de quoi la payer.
    """
    from app.models.game.territory import ResourceType

    return round(sum(
        territory.get_hourly_gain(resource_type=ResourceType.research)
        for territory in user.territories
    ), 2)
