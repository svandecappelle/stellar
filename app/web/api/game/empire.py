# -*- coding: utf-8 -*-

"""
La vue d'empire : tous les mondes d'un joueur dans une galaxie, en une lecture.

    POST /api/galaxy/<name>/empire    les mondes, rattrapes, avec leurs chantiers
    GET  /api/galaxy/<name>/players   qui tient quelque chose ici (moderation)
    POST /api/territory/<id>/grant    poser ou retirer, sans cout ni delai

La regle d'arbitrage vit ici — `require_moderation`, `holder_for` — et sert
aussi a l'arbitrage de la RECHERCHE, qui est reste aupres des routes de
recherche (`technologies.py`) parce qu'il en partage la serialisation. Une
seule definition du droit, deux endroits qui s'en servent : deux copies
auraient fini par diverger, et c'est precisement le genre de divergence qui
ouvre une porte.

Pourquoi un module a part
-------------------------
La premiere route aurait pu rester aupres des autres routes de galaxie ; les
deux suivantes non. Elles ne parlent plus de la galaxie mais de ce qu'un arbitre
a le droit d'y faire, et ce sujet-la merite d'etre lisible d'un bloc : qui peut
entrer, sur quoi, et ce qui en est journalise.

Qui peut entrer
---------------
Un joueur lit son propre empire, et rien d'autre. Un moderateur de la galaxie —
et un administrateur, dont la portee est `*` — lit celui de n'importe quel
joueur de CETTE galaxie, et peut y poser ou retirer des elements sans cout ni
delai. La verification est `User.moderates(galaxy)`, la meme qui garde les
reglages de la galaxie : deux facons de nommer le meme droit auraient fini par
diverger.

La portee est la partie, jamais le serveur : un moderateur de « Milky Way » n'a
aucun droit sur un joueur d'ailleurs, meme si c'est le meme compte.

Ce qui en est journalise
------------------------
Chaque geste pose, jamais les lectures. Un moderateur qui pose dix cuirasses
chez un joueur laisse une ligne nommant la cible, le monde, l'element et la
quantite ; la vue, elle, se relit toute seule chaque minute et noierait le
journal sous des lignes qui ne disent rien.
"""

from flask import request
from flask_login import current_user

from app.application import app, db, serialize
from app.application import json_description
from app.application import login_required
from app.models.audit import Action, record
from app.models.game.buildings import BuildingType
from app.models.game.defense import DefenseType
from app.models.game.fleet import Fleet
from app.models.game.galaxy import Galaxy
from app.models.game.ship import ShipType
from app.models.game.territory import Territory
from app.models.user import User
from app.web.api.exceptions import (
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)

#: Ce qu'un arbitre peut poser, et par quel vocabulaire il le nomme. Une table
#: plutot qu'une suite de `if` : c'est aussi elle qui valide — un nom absent est
#: un 400, jamais une exception qui remonte en 500.
GRANTABLE = {
    'building': BuildingType,
    'defense': DefenseType,
    'ship': ShipType,
}

#: Garde-fou de quantite. Rien ne justifie de poser mille niveaux d'un coup, et
#: une faute de frappe sur un champ libre ne doit pas pouvoir rendre une partie
#: injouable en un clic.
GRANT_MAX = 1000


@app.route('/api/galaxy/<string:name>/empire', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_galaxy_empire(name):
    """
    Tout l'empire d'un joueur dans cette galaxie, en une seule lecture.
    ---
    POST et non GET, pour la meme raison que /api/territory/<id>/update : la
    route RATTRAPE chaque monde avant de le rendre. Les ressources d'un
    territoire ne montent pas toutes seules en base — elles sont creditees au
    moment ou on le regarde — et une vue d'empire qui listerait les stocks sans
    rattraper afficherait les chiffres de la derniere visite, donc des boutons
    « trop cher » sur des mondes qui ont de quoi payer depuis longtemps.

    Ce que /api/galaxy/<name>/territories ne porte pas, et qu'il faut ici : les
    defenses posees, les chantiers en cours, et ce qui tient l'orbite. Les lire
    monde par monde couterait trois appels par planete — vingt mondes, soixante
    allers-retours pour une seule page.

    `player` designe l'empire a lire. Absent, c'est le sien. Celui d'un autre
    n'est ouvert qu'au moderateur de cette galaxie, et la reponse le dit :
    `moderating` est ce qui autorise la console a proposer les gestes gratuits,
    `can_moderate` ce qui lui fait afficher le choix des joueurs.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    me = current_user.get()
    holder, moderating = holder_for(galaxy_name=name, me=me)

    worlds = [
        _world_payload(territory, holder=holder, moderating=moderating)
        for territory in holder.territories
        if territory.galaxy_name == name
    ]

    # L'ordre est celui qu'on lit : systeme par systeme, et dans chaque systeme
    # de l'orbite la plus proche a la plus lointaine. Celui de la relation ne
    # dit rien et change avec les colonisations.
    worlds.sort(key=lambda w: (
        (w['system'] or {}).get('name') or '',
        w.get('position') or 0,
    ))

    return {
        'galaxy_name': name,
        # Le nom de celui dont c'est l'empire, toujours : sans lui, une console
        # qui garde une selection ne saurait pas ce qu'elle montre.
        'player': holder.username,
        'moderating': moderating,
        'can_moderate': me.moderates(name),
        'worlds': worlds,
    }


@app.route('/api/galaxy/<string:name>/players', methods=['GET'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def get_galaxy_players(name):
    """
    Qui tient quelque chose dans cette galaxie.
    ---
    Reserve au moderateur de la partie : c'est la liste dans laquelle il choisit
    l'empire a ouvrir, et elle n'a de sens que pour lui. `/api/admin/players`
    ne convenait pas — elle rend TOUS les comptes du serveur, y compris ceux qui
    ne jouent pas ici, et elle est fermee au moderateur, dont la portee est une
    partie.

    Un nom et un nombre de mondes, rien de plus : de quoi designer quelqu'un et
    voir d'un coup d'oeil qui pese, pas une fiche de compte.
    """
    if not Galaxy.exists(session=db.session, name=name):
        raise NotFoundError('Galaxy does not exists')

    me = current_user.get()
    require_moderation(galaxy_name=name, me=me)

    counted = {}
    for territory in db.session.query(Territory).filter(Territory.user_id != None).all():  # noqa: E711
        if territory.galaxy_name != name or territory.user is None:
            continue
        row = counted.setdefault(territory.user.username, {'username': territory.user.username,
                                                           'worlds': 0})
        row['worlds'] += 1

    return {
        'galaxy_name': name,
        'players': sorted(counted.values(), key=lambda row: row['username'].lower()),
    }


@app.route('/api/territory/<int:territory_id>/grant', methods=['POST'])
@login_required
@serialize
@json_description(file='descriptions/territories.json')
def grant_on_territory(territory_id):
    """
    Poser ou retirer un element sur un monde, sans cout et sans delai.
    ---
    Le geste d'un arbitre : reparer une partie, rendre ce qu'une anomalie a
    mange, eprouver un equilibrage. Il ne passe donc ni par la caisse ni par le
    chantier — `Territory.grant` est ecrit pour cela, et c'est lui qui garde la
    seule regle qui tienne encore ici, celle de la PLACE.

    `amount` est signe : negatif retire, sans jamais passer sous zero. La
    reponse est le monde entier, dans la forme exacte de la vue d'empire, pour
    que la console repeigne la carte sans avoir a relire quoi que ce soit — ce
    qu'elle ne pourrait pas faire de toute facon, les routes de territoire
    etant fermees a qui n'en est pas le proprietaire.
    """
    me = current_user.get()
    territory = Territory.get(id=territory_id)
    if not territory:
        raise NotFoundError('Territory does not exists')
    if not territory.user_id:
        raise BadRequestError("This world belongs to nobody: there is nothing to grant.")

    require_moderation(galaxy_name=territory.galaxy_name, me=me)

    payload = json_body()
    kind = str(payload.get('kind') or '')
    if kind not in GRANTABLE:
        raise BadRequestError(
            "kind must be one of: %s." % ", ".join(sorted(GRANTABLE)))

    name = str(payload.get('name') or '')
    element = next((e for e in GRANTABLE[kind] if e.name == name), None)
    if element is None:
        raise BadRequestError("Unknown %s: %s." % (kind, name or '(none)'))

    try:
        amount = int(payload.get('amount', 1))
    except (TypeError, ValueError):
        raise BadRequestError("amount must be a whole number.")
    if amount == 0:
        raise BadRequestError("amount must not be zero.")
    if abs(amount) > GRANT_MAX:
        raise BadRequestError("amount must stay within %d." % GRANT_MAX)

    # Rattraper AVANT de poser, et c'est tout sauf un detail : la production de
    # la periode ecoulee se compte aux niveaux d'alors. Poser d'abord la
    # crediterait au niveau tout neuf, et le monde recevrait retroactivement ce
    # qu'il n'a jamais produit.
    territory.update_view()

    applied = territory.grant(element, amount=amount)

    record(Action.MODERATION_GRANT,
           galaxy=territory.galaxy_name,
           target=territory.user.username,
           territory_id=territory.id,
           kind=kind,
           element=element.name,
           asked=amount,
           applied=applied)
    db.session.commit()

    return _world_payload(territory, holder=territory.user, moderating=True)


# ── Outillage ───────────────────────────────────────────────────────────────

def json_body():
    """
    La charge utile JSON, vide quand il n'y en a pas.

    `request.json` leve un 415 des que l'appel n'annonce pas de JSON — et lire
    son propre empire n'a rien a envoyer. La console postait donc une requete
    sans corps, parfaitement legitime, a laquelle le serveur repondait « type de
    media non supporte ».
    """
    return request.get_json(silent=True) or {}


def holder_for(galaxy_name, me):
    """
    De qui est l'empire — ou l'arbre — demande, et si on le lit en arbitre.

    Trois cas, et le troisieme merite d'etre dit :

      · aucun nom : c'est le sien, et on y JOUE. C'est la lecture ordinaire,
        celle de tout le monde ;
      · le nom d'un autre : reserve au moderateur de cette galaxie, et c'est un
        arbitrage ;
      · SON PROPRE nom, pose explicitement, par quelqu'un qui modere : c'est un
        arbitrage aussi. Un moderateur arbitre donc son propre empire, mais
        jamais par megarde — il faut l'avoir demande. Les routes de geste ne
        regardent de toute facon que le droit de moderer la galaxie, jamais la
        propriete : refuser ici ce qu'elles acceptent la-bas aurait fait une
        regle differente selon la porte d'entree.

    Un joueur ordinaire qui pose son propre nom retombe sur le premier cas :
    lire son empire ne peut pas dependre de la facon dont on le demande.

    Le nom d'un compte qui n'existe pas rend 404 et non 403 : refuser l'acces a
    un compte absent apprendrait, par la difference, quels noms existent.
    """
    wanted = ((json_body().get('player')) or '').strip()
    if not wanted or (wanted == me.username and not me.moderates(galaxy_name)):
        return me, False

    require_moderation(galaxy_name=galaxy_name, me=me)

    if wanted == me.username:
        return me, True

    if not User.exists(username=wanted):
        raise NotFoundError('Player does not exists')

    return User.get(username=wanted), True


def require_moderation(galaxy_name, me):
    """
    Le droit d'arbitrer cette partie, ou un refus.

    Le refus est journalise par l'`after_request` du module d'audit, comme tous
    les refus : quelqu'un qui essaie d'entrer chez un autre joueur est
    exactement le genre de ligne qu'on veut retrouver.
    """
    if me is None or not me.moderates(galaxy_name):
        raise PermissionDeniedError(
            "Only a moderator of this galaxy can do this.")


def _world_payload(territory, holder, moderating=False):
    """
    Un monde tel que la vue d'empire le lit.

    Le territoire est rattrape ici : c'est le seul etat sur lequel quelqu'un
    peut decider une depense.

    `holding` est repris du point de vue du PROPRIETAIRE quand un moderateur
    regarde. Sans cela le bloc serait nul — il n'est rendu qu'a celui dont c'est
    le monde, et pour une bonne raison : dire d'un monde ennemi qu'il est isole
    publierait la carte de son reseau. Un arbitre, lui, doit justement voir
    venir la secession qu'on vient lui signaler.
    """
    territory.update_view()

    data = dict(
        territory.serialize,
        defenses=list(territory.defenses),
        events=list(territory.territory_events),
        # Ce qui tient l'orbite d'ici, par type. Un vaisseau assemble quitte la
        # planete pour une flotte : sans cette ligne, la vue d'empire proposerait
        # de construire des coques sans jamais dire combien il y en a deja.
        orbit=_ships_in_orbit_of(territory, holder),
    )

    if moderating:
        data['holding'] = territory.holding_status(user=holder)

    return data


def _ships_in_orbit_of(territory, user):
    """
    Les vaisseaux du joueur en orbite de ce monde, par type.
    ---
    Agrege ici et non chez le client : la console n'a pas les flottes du systeme
    sous la main dans la vue d'empire, et les lui envoyer entieres pour qu'elle
    en fasse une somme ferait voyager tout le detail d'une flotte pour un
    compteur.
    """
    counts = {}
    for fleet in Fleet.in_orbit_of(territory=territory, user=user):
        for ship in fleet.ships:
            if ship.count:
                counts[ship.type.name] = counts.get(ship.type.name, 0) + ship.count
    return counts
