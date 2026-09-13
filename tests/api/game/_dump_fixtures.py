# -*- coding: utf-8 -*-

"""
Ecrit les echantillons que lit le controle batch du client Unity.

Un generateur, pas un test : il ne verifie rien que la suite ne verifie deja.
Il ne s'execute que si on lui dit ou ecrire, sinon un `pytest` ordinaire irait
deposer des fichiers hors du depot.

    FIXTURE_OUT=.../Stellar-Unity/Tests \
        python -m pytest tests/api/game/_dump_fixtures.py -s

`FIXTURE_OUT` designe le dossier `Tests` du projet Unity ; chaque famille
d'echantillons va dans son sous-dossier, celui que son controle lit.

Les echantillons servent aux controles en mode batch du client : `JsonUtility`
apparie par nom de champ et en silence, une cle renommee ici laisse le client
a zero sans rien dire. Un echantillon perime est donc pire qu'absent — il fait
passer un controle sur un contrat qui n'existe plus.
"""

from datetime import datetime, timedelta
import io
import json
import os

import pytest

from app.models.game.buildings import BuildingType
from app.models.game.planet import PlanetArchetype
from app.models.game.ship import ShipType
from app.models.game.territory import Territory

from tests.api.game.colonisation import grant, me, orbit, world


OUT = os.environ.get('FIXTURE_OUT')


def write(name, payload, family='DevelopmentFixtures'):
    folder = os.path.join(OUT, family)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, name)
    with io.open(path, 'w', encoding='utf-8') as out:
        out.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    print('wrote %s' % path)


@pytest.mark.skipif(not OUT, reason="FIXTURE_OUT absent : rien a ecrire")
@pytest.mark.usefixtures("authenticate_as_user")
def test_dump(client, session, base_universe):
    user = me(session, base_universe)

    colony = user.territories[0]
    colony.archetype = PlanetArchetype.telluric
    session.commit()

    answer = client.get('/api/territory/%d' % colony.id)
    assert answer.status_code == 200
    write('territory-colony.json', answer.json)

    grant(session, user, forage=3)
    target = world(session, base_universe, PlanetArchetype.gas_giant)
    orbit(session, target, user, ShipType.ExtractionPlatform)
    assert client.post('/api/territory/%d' % target.id).status_code in (200, 201)

    platform = Territory.get(id=target.id)
    answer = client.get('/api/territory/%d' % platform.id)
    assert answer.status_code == 200
    write('territory-platform.json', answer.json)

    # Le monde qui se meurt : coupe du reseau, eteint, et son compte a rebours
    # en cours. C'est le seul cas pour lequel l'alerte existe, et le seul ou la
    # date de secession est remplie.
    dying = world(session, base_universe, PlanetArchetype.telluric, position=4)
    dying.assign(user=user)
    dying.is_capital = False
    dying.stability = 0
    dying.unstable_since = datetime.utcnow() - timedelta(days=1, hours=6)
    session.commit()

    answer = client.get('/api/territory/%d' % dying.id)
    assert answer.status_code == 200
    assert answer.json['holding']['deactivated'] is True
    write('territory-dying.json', answer.json)

    # Le monde d'un autre, tel qu'il apparait dans la liste d'un systeme : sans
    # bloc de tenue. C'est l'echantillon qui prouve que l'alerte SE TAIT quand
    # le serveur ne dit rien — `JsonUtility` construit l'objet imbrique meme
    # absent, et le bloc vide s'y lirait sinon comme « monde isole ».
    from app.models.user import User

    rival = User.new(username="rivale", password="motdepasse",
                     email="rivale@testing.com")
    foreign = world(session, base_universe, PlanetArchetype.telluric, position=5)
    foreign.assign(user=rival)
    session.commit()

    answer = client.get('/api/system/%d/territories' % foreign.system_id)
    assert answer.status_code == 200
    shown = next(t for t in answer.json['territories'] if t['id'] == foreign.id)
    assert shown['holding'] is None
    write('territory-foreign.json', shown)

    # Une ligne ouverte, avec ses flux dans les deux sens : ce que lit le
    # panneau de commerce. Posee par le modele plutot que par la route — c'est
    # la FORME de la reponse qu'on echantillonne, pas le geste qui l'ouvre.
    from app.models.game.trade import TradeLine

    line = TradeLine(user_id=user.id, origin_id=colony.id,
                     destination_id=platform.id,
                     flows=[{'resource': 'food', 'rate': 280.0, 'to_origin': False},
                            {'resource': 'hydrogen', 'rate': 120.0, 'to_origin': True}])
    session.add(line)
    colony.get_building(building_type=BuildingType.depot).level = 2
    platform.get_building(building_type=BuildingType.depot).level = 1
    session.commit()

    answer = client.get('/api/trade')
    assert answer.status_code == 200
    assert answer.json['lines'][0]['throughput'] > 0
    write('trade-lines.json', answer.json)


@pytest.mark.skipif(not OUT, reason="FIXTURE_OUT absent : rien a ecrire")
@pytest.mark.usefixtures("authenticate_as_user")
def test_dump_empire(client, session, base_universe):
    """
    Un empire entier en mauvais etat, pour le fil d'alertes du client.

    Le fil n'invente aucune regle : la chaine qui tue un monde — coupe du
    reseau, stabilite qui descend d'un point par heure, extinction a zero,
    secession trois jours plus tard — est appliquee ici depuis toujours, et le
    client recevait deja les champs qui la racontent. Il les jetait.

    Quatre mondes, un par branche de la decision :

      · la capitale, qui va bien — aucune alerte ;
      · un monde relie mais ETRANGLE : une flotte etrangere tient l'orbite, la
        ligne reste ouverte et ne raccorde plus rien ;
      · un monde raccorde et AFFAME — reserve vide, recolte insuffisante ;
      · un monde eteint dont la secession est datee — le seul qui porte une
        echeance.

    Les deux reponses sont prises A LA FIN, apres que tout est en place : elles
    decrivent le meme instant, comme les deux appels que le client enchaine.
    Un echantillon de mondes pris avant les lignes aurait montre un empire qui
    n'a jamais existe.

    Un ordre de gravite recopie a la main dans le client divergerait au premier
    equilibrage. C'est la reponse du serveur qui tranche, et c'est elle qu'on
    echantillonne.
    """
    from app.models.game.fleet import Fleet
    from app.models.game.trade import TradeLine
    from app.models.user import User

    user = me(session, base_universe)

    capital = user.territories[0]
    capital.is_capital = True
    capital.archetype = PlanetArchetype.telluric
    capital.get_building(building_type=BuildingType.depot).level = 3
    session.commit()

    # Le monde etrangle : relie a la capitale, et pourtant coupe.
    squeezed = world(session, base_universe, PlanetArchetype.telluric, position=4)
    squeezed.assign(user=user)
    squeezed.is_capital = False
    squeezed.stability = 40
    squeezed.get_building(building_type=BuildingType.depot).level = 1
    session.commit()

    # L'affame : raccorde pour de bon, mais avec plus de bouches que la
    # recolte n'en couvre et rien dans la reserve.
    hungry = world(session, base_universe, PlanetArchetype.telluric, position=5)
    hungry.assign(user=user)
    hungry.is_capital = False
    hungry.get_building(building_type=BuildingType.depot).level = 1
    hungry.food = 0
    hungry.population = (hungry.population_capacity * 10) + 1000
    session.commit()

    # L'eteint, et son compte a rebours en cours.
    dying = world(session, base_universe, PlanetArchetype.telluric, position=6)
    dying.assign(user=user)
    dying.is_capital = False
    dying.stability = 0
    dying.unstable_since = datetime.utcnow() - timedelta(days=1, hours=6)
    session.commit()

    session.add(TradeLine(
        user_id=user.id, origin_id=capital.id, destination_id=squeezed.id,
        flows=[{'resource': 'food', 'rate': 100.0, 'to_origin': False}]))
    session.add(TradeLine(
        user_id=user.id, origin_id=capital.id, destination_id=hungry.id,
        flows=[{'resource': 'food', 'rate': 100.0, 'to_origin': False}]))
    session.commit()

    # La flotte qui etrangle. Le blocus est un robinet, pas une demolition :
    # la ligne reste ouverte, et c'est pour cela qu'aucune fiche de monde ne
    # dit a elle seule ce qui se passe.
    rival = User.new(username="assiegeante", password="motdepasse",
                     email="assiegeante@testing.com")
    session.commit()
    session.add(Fleet(user_id=rival.id, system_id=squeezed.system_id))
    session.commit()

    answer = client.get('/api/territories')
    assert answer.status_code == 200
    worlds = {t['id']: t for t in answer.json['territories']}

    assert worlds[capital.id]['holding']['connected'] is True, \
        "la capitale est raccordee par definition"
    assert worlds[squeezed.id]['holding']['connected'] is False, \
        "une ligne bloquee ne raccorde plus rien"
    assert worlds[squeezed.id]['holding']['deactivated'] is False, \
        "coupe n'est pas eteint : la stabilite descend encore"
    assert worlds[hungry.id]['holding']['connected'] is True, \
        "l'affame est bien au bout d'une ligne coulante"
    assert worlds[hungry.id]['starving'] is True, \
        "reserve vide et recolte insuffisante : le monde a faim"
    assert worlds[dying.id]['holding']['secedes_at'], \
        "le monde eteint doit porter sa date de secession"
    write('territories-empire.json', answer.json, family='AlertFixtures')

    answer = client.get('/api/trade')
    assert answer.status_code == 200
    blocked = [l for l in answer.json['lines'] if l['blockaded']]
    flowing = [l for l in answer.json['lines'] if not l['blockaded']]
    assert blocked, "la flotte etrangere doit bloquer une ligne"
    assert flowing, "l'autre ligne doit rester coulante"
    write('trade-blockade.json', answer.json, family='AlertFixtures')


@pytest.mark.skipif(not OUT, reason="FIXTURE_OUT absent : rien a ecrire")
@pytest.mark.usefixtures("authenticate_as_user")
def test_dump_claims(client, session, base_universe):
    """
    Les offres de prise d'un systeme, pour `PlanetContextWiringCheck`.

    Le menu contextuel du client de jeu dessine ses entrees a partir de ce bloc
    `claim` : le geste, la coque a amener, ce qui manque et pourquoi. Il ne
    rejoue aucune regle — mais il en LIT une, et une cle renommee ici le
    laisserait proposer « coloniser » sur un monde que le serveur refuse, ou
    l'inverse, sans rien dire.

    Un systeme et quatre mondes, chacun dans un etat different : celui qu'on
    tient, celui qu'un autre tient, un monde libre a coloniser, et un corps sans
    surface a arrimer. C'est la table de decision entiere du menu.

    Le catalogue part avec : c'est lui qui nomme toutes les coques du serveur, et
    le controle s'en sert pour verifier que le chantier du client peut construire
    celles qu'une prise reclame. Trois d'entre elles manquaient — dont le
    vaisseau de colonisation — et rien ne le disait : le joueur ne pouvait tout
    simplement pas coloniser.
    """
    user = me(session, base_universe)

    # Le systeme qu'on echantillonne : celui du monde de depart, pour que la
    # reponse porte a la fois un monde a nous et des mondes libres.
    home = user.territories[0]
    system = home.system

    # Un monde libre et colonisable, dans le meme systeme.
    free = Territory.create(system_id=system.id, position_in_system=7)
    free.archetype = PlanetArchetype.telluric
    free.deposits = PlanetArchetype.telluric.roll_deposits()

    # Un corps sans surface : celui-la s'arrime, il ne se colonise pas.
    giant = Territory.create(system_id=system.id, position_in_system=8)
    giant.archetype = PlanetArchetype.gas_giant
    giant.deposits = PlanetArchetype.gas_giant.roll_deposits()

    # Et le monde d'un autre, qu'aucune coque ne prendra.
    from app.models.user import User

    rival = User.new(username="voisine", password="motdepasse",
                     email="voisine@testing.com")
    taken = Territory.create(system_id=system.id, position_in_system=9)
    taken.archetype = PlanetArchetype.telluric
    taken.deposits = PlanetArchetype.telluric.roll_deposits()
    session.commit()
    taken.assign(user=rival)
    session.commit()

    answer = client.get('/api/system/%d/territories' % system.id)
    assert answer.status_code == 200

    offers = {t['id']: t['claim'] for t in answer.json['territories']
              if t.get('claim')}
    assert offers[free.id]['hull'] == ShipType.ColonyShip.name, \
        "un monde libre se prend avec un vaisseau de colonisation"
    assert offers[giant.id]['hull'] == ShipType.ExtractionPlatform.name, \
        "un corps sans surface se prend avec une plateforme"
    assert offers[taken.id]['taken'] is True
    write('system-territories.json', answer.json, family='ClaimFixtures')

    catalogue = client.get('/api/catalog')
    assert catalogue.status_code == 200
    assert catalogue.json['ships'], "le catalogue ne nomme aucune coque"
    write('catalog.json', catalogue.json, family='ClaimFixtures')

    # Le meme systeme, vu par quelqu'un qui n'a encore rien : sa premiere prise
    # ne demande ni coque ni technologie, et c'est le seul cas ou `first` vaut
    # vrai. Le client en depend — c'est ainsi qu'un compte neuf s'installe — et
    # c'est le seul chemin de colonisation qui marchait avant que le chantier
    # ne sache construire un vaisseau de colonisation.
    newcomer = User.new(username="nouvelle", password="motdepasse",
                        email="nouvelle@testing.com")
    session.commit()
    assert newcomer.id
    assert client.post('/api/auth/login', json={
        "username": "nouvelle", "password": "motdepasse"}).status_code == 200

    answer = client.get('/api/system/%d/territories' % system.id)
    assert answer.status_code == 200
    offers = [t['claim'] for t in answer.json['territories'] if t.get('claim')]
    assert any(o['first'] and o['available'] for o in offers),         "un compte sans monde doit pouvoir s'installer quelque part"
    assert all(not o['hull'] for o in offers if o['first']),         "une premiere prise ne demande aucune coque"
    write('system-territories-newcomer.json', answer.json, family='ClaimFixtures')


@pytest.mark.skipif(not OUT, reason="FIXTURE_OUT absent : rien a ecrire")
@pytest.mark.usefixtures("authenticate_as_user")
def test_dump_research(client, session, base_universe):
    """
    L'arbre technologique et l'etat du joueur dedans, pour
    `ResearchWiringCheck`.

    Ils dataient d'avant le retrait des couts en materiaux : le controle
    passait, mais sur un contrat que le serveur n'ecrivait plus.
    """
    tree = client.get('/api/technologies/tree')
    assert tree.status_code == 200
    assert tree.json['nodes'], "l'arbre est vide"
    write('api-tree.json', tree.json, family='ResearchFixtures')

    # Une recherche EN COURS : c'est la moitie interessante de l'etat — la
    # fiche d'un noeud en chantier porte un anneau, un compte a rebours et un
    # bouton d'annulation que rien d'autre n'exerce.
    user = me(session, base_universe)
    user.add_research(500000)
    session.commit()

    started = client.post('/api/technology/extraction')
    assert started.status_code == 200, started.json

    state = client.get('/api/technologies')
    assert state.status_code == 200
    assert state.json['pending'], "aucune recherche en cours"
    write('api-state.json', state.json, family='ResearchFixtures')
