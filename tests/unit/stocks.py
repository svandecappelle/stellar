# -*- coding: utf-8 -*-

"""
Les lots de vaisseaux et de batteries : ce qu'on en compte.

Deux modeles presque jumeaux -- un lot de vaisseaux dans une flotte, une
batterie sur un territoire -- avec les memes deux methodes pour un compteur, et
les memes deux pieges deja tombes une fois :

  · `increment` ignorait son argument et ajoutait toujours un. Une livraison de
    six vaisseaux en posait un seul, et la commande semblait s'evaporer ;
  · `decrement` avait son ternaire a l'envers : quand on lui demandait plus que
    le stock, il retirait le montant demande et le compte passait negatif. Une
    flotte pouvait compter moins que rien.

Les deux se lisent en trois lignes ici, et aucune des deux ne se voit dans une
reponse d'API tant que la quantite demandee vaut un.

Les tables de couts sont eprouvees comme celles des batiments : ce dont le reste
du code depend -- des cles qui nomment des ressources qui existent -- plutot que
les nombres eux-memes.
"""

import pytest

from app.models.game.defense import Defense, DefenseType
from app.models.game.ship import Ship, ShipType
from app.models.game.territory import ResourceType


#: Les deux familles se comportent pareil : on les eprouve ensemble.
UNIT_TYPES = list(ShipType) + list(DefenseType)


def a_lot_of(unit_type, count=0):
    """Un lot du type demande, vaisseaux ou batterie."""
    if isinstance(unit_type, ShipType):
        return Ship(fleet_id=1, type=unit_type, count=count)
    lot = Defense(territory_id=1, type=unit_type)
    lot.count = count
    return lot


class TestCounting:

    @pytest.mark.parametrize("unit_type", [ShipType.Fighter, DefenseType.Coilgun])
    def test_a_delivery_adds_the_number_delivered(self, unit_type):
        """
        Le compte demande, et non un par appel.
        ---
        Une commande porte sur plusieurs unites : c'est ce nombre-la qui doit
        arriver, sans quoi neuf vaisseaux sur dix disparaissent en silence.
        """
        lot = a_lot_of(unit_type)

        lot.increment(count=6)

        assert lot.count == 6

    @pytest.mark.parametrize("unit_type", [ShipType.Fighter, DefenseType.Coilgun])
    def test_one_at_a_time_stays_the_default(self, unit_type):
        lot = a_lot_of(unit_type, count=2)

        lot.increment()

        assert lot.count == 3

    @pytest.mark.parametrize("unit_type", [ShipType.Fighter, DefenseType.Coilgun])
    def test_losses_take_what_there_is_and_no_more(self, unit_type):
        """
        Un compte ne passe jamais sous zero.
        ---
        Un lot negatif se propagerait partout : dans la taille de la flotte,
        dans la composition envoyee au client, et dans toute somme qui les
        additionne.
        """
        lot = a_lot_of(unit_type, count=3)

        lot.decrement(count=10)

        assert lot.count == 0

    @pytest.mark.parametrize("unit_type", [ShipType.Fighter, DefenseType.Coilgun])
    def test_a_partial_loss_leaves_the_rest(self, unit_type):
        lot = a_lot_of(unit_type, count=10)

        lot.decrement(count=4)

        assert lot.count == 6

    @pytest.mark.parametrize("unit_type", [ShipType.Fighter, DefenseType.Coilgun])
    def test_a_lot_says_what_it_is_and_how_many(self, unit_type):
        lot = a_lot_of(unit_type, count=4)

        assert lot.serialize == {'quantity': 4, 'type': unit_type.name}


class TestTheCatalogue:

    def test_every_cost_names_a_resource_the_game_knows(self):
        """
        Une cle inconnue est un cout qui ne se paie jamais.
        ---
        `Territory.spend` convertit chaque cle en `ResourceType` : un nom
        inconnu y leve, et la commande echoue au moment du paiement plutot qu'a
        la verification.
        """
        known = {resource.name for resource in ResourceType}

        for unit_type in UNIT_TYPES:
            assert set(unit_type.cost) <= known, unit_type.name

    def test_nothing_is_free(self):
        for unit_type in UNIT_TYPES:
            assert any(amount > 0 for amount in unit_type.cost.values()), \
                unit_type.name

    def test_everything_that_flies_or_fires_needs_a_crew(self):
        """
        Chaque unite coute de la population.
        ---
        C'est le seul lien entre la colonie et sa flotte : sans equipage a
        fournir, un monde vide construirait autant qu'un monde peuple, et la
        nourriture ne servirait a rien.
        """
        for unit_type in UNIT_TYPES:
            assert unit_type.cost.get('population', 0) > 0, unit_type.name

    def test_everything_has_a_hull(self):
        """L'integrite fixe la duree d'assemblage : zero la rendrait instantanee."""
        for unit_type in UNIT_TYPES:
            assert unit_type.value['integrity'] > 0, unit_type.name

    def test_a_heavier_ship_takes_longer_to_assemble(self, stub):
        """
        La duree suit l'integrite : un vaisseau-mere ne se monte pas comme un
        chasseur.
        """
        shipyard = stub(level=1)

        durations = [(t.duration(shipyard=shipyard), t.value['integrity'])
                     for t in ShipType]

        assert sorted(durations) == sorted(durations, key=lambda pair: pair[1])
        assert (ShipType.MotherShip.duration(shipyard=shipyard)
                > ShipType.Fighter.duration(shipyard=shipyard))

    def test_the_end_game_ships_are_the_dearest(self):
        """
        Le vaisseau-mere et la station orbitale sont des objectifs.
        ---
        Ils sont les seuls a demander du neutronium, que seule une anomalie
        produit : c'est ce qui en fait une fin de partie et non un achat.
        """
        needing_neutronium = [
            t for t in ShipType if t.cost.get('neutronium', 0) > 0]

        assert set(needing_neutronium) == {
            ShipType.MotherShip, ShipType.OrbitalStation}

    def test_a_unit_is_found_by_its_name(self):
        assert ShipType.get_by_name('Cruiser') is ShipType.Cruiser
        assert DefenseType.get_by_name('Shield') is DefenseType.Shield
