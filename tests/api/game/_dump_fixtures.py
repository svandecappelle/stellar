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
