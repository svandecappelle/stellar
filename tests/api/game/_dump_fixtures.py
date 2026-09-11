# -*- coding: utf-8 -*-

"""
Ecrit les echantillons que lit le controle batch du client Unity.

Un generateur, pas un test : il ne verifie rien que la suite ne verifie deja.
Il ne s'execute que si on lui dit ou ecrire, sinon un `pytest` ordinaire irait
deposer des fichiers hors du depot.

    FIXTURE_OUT=.../Stellar-Unity/Tests/DevelopmentFixtures \
        python -m pytest tests/api/game/_dump_fixtures.py -s

Les echantillons servent a `DevelopmentWiringCheck` cote Unity : `JsonUtility`
apparie par nom de champ et en silence, une cle renommee ici laisse le client
a zero sans rien dire.
"""

import io
import json
import os

import pytest

from app.models.game.planet import PlanetArchetype
from app.models.game.ship import ShipType
from app.models.game.territory import Territory

from tests.api.game.colonisation import grant, me, orbit, world


OUT = os.environ.get('FIXTURE_OUT')


def write(name, payload):
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    path = os.path.join(OUT, name)
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
