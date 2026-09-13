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

L'arbitrage
-----------
Deux routes de plus, reservees au moderateur d'une galaxie :

    POST /api/galaxy/<name>/research        l'arbre d'un joueur, lu en arbitre
    POST /api/galaxy/<name>/research/grant  poser ou retirer un niveau

Elles vivent ici et non dans le module d'empire parce qu'elles partagent la
serialisation de l'etat — un arbitre doit lire exactement ce que le joueur lit,
sinon il arbitre sur autre chose. Le DROIT, lui, ne se recopie pas : il vient
de `empire.require_moderation`, qui garde deja la vue d'empire.

Une galaxie dans le chemin, pour une recherche qui n'en a pas
------------------------------------------------------------
La portee d'un moderateur est une partie ; celle d'une technologie est le
joueur, toutes galaxies confondues. Un niveau pose ici suit donc le joueur
partout ailleurs, et c'est pourquoi le droit doit etre ANCRE : la galaxie du
chemin est celle qu'on modere, et le geste exige que le joueur y tienne quelque
chose. Sans cet ancrage, moderer une partie vide aurait donne barre sur les
empires de toutes les autres.
"""

from flask import jsonify, request
from flask_login import current_user

from app.models.audit import Action, record
from app.application import app, db, serialize
from app.application import login_required
from app.application import json_description
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import TechnologyType, tree
from app.web.api.exceptions import BadRequestError, NotFoundError
from app.web.api.game.empire import (
    GRANT_MAX,
    holder_for,
    json_body,
    require_moderation,
)


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
    state = technology_state(me)
    db.session.commit()
    return jsonify(state)


def technology_state(user):
    """
    L'etat d'un joueur dans l'arbre : niveaux, recherches en cours, reserve.
    ---
    Pose a part pour etre lisible d'un AUTRE joueur que celui qui est connecte :
    c'est ce qu'un arbitre ouvre. Il doit lire exactement ce que le joueur lit,
    sans quoi il arbitre sur autre chose que ce qui se joue.
    """
    # Les lignes manquantes sont posees avant la lecture. Un compte cree sans
    # territoire puis installe plus tard n'en avait aucune, et l'arbre lui
    # apparaissait entier mais sans etat : chaque noeud s'affichait, aucun ne
    # s'ouvrait. C'est aussi ce qui rattrape un arbre agrandi dont la migration
    # n'a pas encore tourne.
    Technology.ensure(user=user)

    # `modifiers` encaisse au passage les recherches arrivees a terme : ce qui
    # est fini doit apparaitre fini, et compter dans les couts annonces juste
    # en dessous.
    modifiers = user.modifiers
    technologies = sorted(
        Technology.all(user=user),
        key=lambda t: (list(TechnologyType).index(t.type)))

    levels = Technology.levels(user=user)
    branch_totals = Technology.branch_levels(user=user)
    pending = Technology.pending(user=user)
    ordered = {e.extra_args.get('type'): e.extra_args for e in pending}

    return {
        'research': round(float(user.research or 0.0), 2),
        'research_gain': _hourly_research(user),
        'slots': Technology.slots(user=user, modifiers=modifiers),
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
    }


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


@app.route('/api/galaxy/<string:name>/research', methods=['POST'])
@login_required
@json_description(file='descriptions/technologies.json')
def get_player_research(name):
    """
    L'arbre d'un joueur, lu par un arbitre.
    ---
    Meme charge utile que `/api/technologies` — c'est la meme fonction qui la
    batit — plus de quoi savoir ce qu'on regarde : `player`, `moderating`,
    `can_moderate`. Sans nom dans le corps, c'est son propre arbre, et la route
    ne fait alors rien de plus que la lecture ordinaire.

    POST pour pouvoir porter le nom du joueur dans le corps plutot que dans le
    chemin : l'arbre est une lecture, mais le nom d'un joueur n'a pas a trainer
    dans les journaux d'acces d'un proxy.
    """
    me = current_user.get()
    target, moderating = holder_for(galaxy_name=name, me=me)

    state = technology_state(target)
    db.session.commit()

    return jsonify(dict(
        state,
        galaxy_name=name,
        player=target.username,
        moderating=moderating,
        can_moderate=me.moderates(name),
    ))


@app.route('/api/galaxy/<string:name>/research/grant', methods=['POST'])
@login_required
@json_description(file='descriptions/technologies.json')
def grant_technology(name):
    """
    Poser ou retirer des niveaux de recherche, sans cout et sans delai.
    ---
    Le pendant de `/api/territory/<id>/grant`, pour ce qui ne pend a aucun
    monde. `Technology.increase(now=True)` existait deja pour cela : une faveur,
    dit-il — une avance de partie, un avantage de faction — et c'est exactement
    ce qu'un arbitre pose. Rien n'est facture, aucun emplacement n'est occupe,
    aucun prerequis n'est exige : un arbitre qui devrait remonter la branche
    entiere pour offrir son sommet ne reparerait jamais rien.

    Ce qui tient encore : le PLAFOND du noeud. Un niveau au-dela de son maximum
    n'existe pas dans les tables d'effets, et rien ne le lirait — la quantite
    est donc rabotee, et la reponse dit ce qui a ete applique.

    `choice` n'a de sens que sur une doctrine. Ramene a zero, le noeud rend sa
    voie : un arbitre qui retire une doctrine rend au joueur le choix qu'elle
    avait fige, sinon il lui laisserait un noeud a zero deja engage.
    """
    me = current_user.get()
    require_moderation(galaxy_name=name, me=me)

    payload = json_body()
    target, _ = holder_for(galaxy_name=name, me=me)
    if target.id == me.id and not (payload.get('player') or '').strip():
        # Poser chez soi se demande : sans nom, la route rendrait le geste au
        # demandeur par defaut, ce qui n'est jamais ce qu'on voulait dire.
        raise BadRequestError("player is required.")

    # La recherche suit le joueur partout : le droit de la toucher doit etre
    # ancre dans une galaxie ou il joue. Moderer une partie ou il n'a rien ne
    # donne pas barre sur son empire d'ailleurs.
    if not any(t.galaxy_name == name for t in target.territories):
        raise BadRequestError(
            "%s holds nothing in %s." % (target.username, name))

    tech_type = TechnologyType.get_by_name(str(payload.get('name') or ''))
    if tech_type is None:
        raise NotFoundError("Unknown technology: %s." % payload.get('name'))

    try:
        amount = int(payload.get('amount', 1))
    except (TypeError, ValueError):
        raise BadRequestError("amount must be a whole number.")
    if amount == 0:
        raise BadRequestError("amount must not be zero.")
    if abs(amount) > GRANT_MAX:
        raise BadRequestError("amount must stay within %d." % GRANT_MAX)

    Technology.ensure(user=target)
    technology = Technology.get(user=target, type=tech_type)
    applied = _move_level(technology, amount=amount, choice=payload.get('choice'))

    record(Action.MODERATION_GRANT,
           galaxy=name,
           target=target.username,
           kind='technology',
           element=tech_type.name,
           asked=amount,
           applied=applied,
           choice=payload.get('choice'))

    target.forget_modifiers()
    state = technology_state(target)
    db.session.commit()

    return jsonify(dict(
        state,
        galaxy_name=name,
        player=target.username,
        moderating=True,
        can_moderate=True,
        applied=applied,
    ))


def _move_level(technology, amount, choice=None):
    """
    Monter ou descendre un noeud, en restant dans ses bornes.

    :return: le nombre de niveaux reellement franchis, du signe de `amount`
    """
    level = technology.level or 0

    if amount > 0:
        ceiling = technology.type.max_level
        applied = min(amount, max(0, ceiling - level))
        for _ in range(applied):
            # Un par un, et par la methode du modele : c'est elle qui sait ce
            # qu'un niveau veut dire sur une doctrine comme sur un noeud infini.
            technology.increase(now=True, choice=choice)
        return applied

    applied = min(-amount, level)
    technology.level = level - applied
    if not technology.level:
        technology.choice = None
    return -applied


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
