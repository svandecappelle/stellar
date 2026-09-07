# -*- coding: utf-8 -*-

"""
La recherche, et les avantages de faction qui la modifient.

Les deux sont reunis ici parce qu'ils ne se rencontrent nulle part ailleurs :
une faction est le seul objet du jeu capable de changer une duree de recherche,
et la recherche est le seul endroit ou cet avantage-la s'applique.

L'application d'un avantage est un calcul de trois lignes, sans etat et sans
base -- et pourtant c'est elle qui decide de ce que vaut le choix d'une faction
en debut de partie. Elle merite d'etre lue de pres, notamment sur le filtrage
par portee : un avantage sur le silicium ne doit pas s'appliquer au titane, et
un avantage sans portee doit s'appliquer a tout ce qui releve de sa categorie.

Les technologies, elles, appartiennent au joueur et non a une galaxie : c'est
pourquoi aucun reglage de partie ne les touche, et pourquoi rien de ce fichier
n'a besoin de `GalaxySettings`.
"""

from datetime import datetime, timedelta

import pytest

from app.models.game.community.faction import (
    Faction, FactionAdvantages, FactionAdvantageScope, FactionAdvantageType)
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import (
    EquationType, TechnologyEquations, TechnologyType)
from app.models.game.territory import ResourceType
from app.models.user import User


#: Une date fixe : les modeles horodatent a l'ecriture, et rien n'est ecrit ici.
MOMENT = datetime(2026, 1, 1, 12, 0, 0)


def a_faction(*advantages):
    """
    Une faction et ses avantages, en memoire.
    ---
    `Faction.initialize` ecrit les trois factions du jeu en base ; ce qu'on veut
    eprouver est la regle d'application, pas le contenu de cette table.
    """
    faction = Faction(name="Cobayes")
    for advantage_type, scope, args in advantages:
        faction.advantages.append(FactionAdvantages(
            faction_id=None,
            advantage_type=advantage_type,
            advantage_scope=scope,
            advantage_scope_args=args,
        ))
    return faction


class TestFactionAdvantages:

    def test_an_advantage_lifts_what_it_covers(self):
        faction = a_faction((
            FactionAdvantageType.Production,
            FactionAdvantageScope.Resource,
            {'percentage': 10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == 110

    def test_an_advantage_of_another_category_does_not_apply(self):
        """
        Un bonus sur les vaisseaux ne touche pas la production.
        ---
        C'est la portee qui donne son caractere a une faction : sans ce filtre,
        les trois factions du jeu auraient exactement les memes effets.
        """
        faction = a_faction((
            FactionAdvantageType.Power,
            FactionAdvantageScope.Ships,
            {'percentage': 10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == 100

    def test_a_named_scope_applies_to_that_one_alone(self):
        """
        Les technocrates gagnent sur le silicium, pas sur tout.
        ---
        Chaque faction a une ressource de predilection : l'avantage porte le nom
        de cette ressource, et ne doit rien donner sur les autres.
        """
        faction = a_faction((
            FactionAdvantageType.Production,
            FactionAdvantageScope.Resource,
            {'percentage': 50, 'scope': ResourceType.silicium.name},
        ))

        assert faction.apply(
            obj=100,
            advantage_scope=FactionAdvantageScope.Resource,
            scope=ResourceType.silicium.name) == 150
        assert faction.apply(
            obj=100,
            advantage_scope=FactionAdvantageScope.Resource,
            scope=ResourceType.titanium.name) == 100

    def test_an_advantage_without_a_named_scope_covers_its_whole_category(self):
        faction = a_faction((
            FactionAdvantageType.Production,
            FactionAdvantageScope.Resource,
            {'percentage': 20},
        ))

        for resource in (ResourceType.iron, ResourceType.credits):
            assert faction.apply(
                obj=100,
                advantage_scope=FactionAdvantageScope.Resource,
                scope=resource.name) == 120

    def test_a_negative_percentage_takes_away(self):
        """
        Le meme calcul sert aux avantages et aux reductions.
        ---
        Les technocrates cherchent dix pour cent plus vite : l'avantage est un
        pourcentage negatif sur une duree, pas une regle a part.
        """
        faction = a_faction((
            FactionAdvantageType.TimeReduce,
            FactionAdvantageScope.Technologies,
            {'percentage': -10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Technologies) == 90

    def test_advantages_of_the_same_scope_add_up(self):
        faction = a_faction(
            (FactionAdvantageType.Production, FactionAdvantageScope.Resource,
             {'percentage': 10}),
            (FactionAdvantageType.Production, FactionAdvantageScope.Resource,
             {'percentage': 10, 'scope': ResourceType.iron.name}),
        )

        assert faction.apply(
            obj=100,
            advantage_scope=FactionAdvantageScope.Resource,
            scope=ResourceType.iron.name) == pytest.approx(121)

    def test_a_faction_without_advantages_changes_nothing(self):
        assert a_faction().apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == 100

    def test_a_faction_says_who_it_is(self):
        faction = a_faction()
        faction.id = 3

        assert faction.serialize == {'id': 3, 'name': "Cobayes"}


class TestTechnologyCatalogue:

    def test_every_cost_names_a_resource_the_game_knows(self):
        known = {resource.name for resource in ResourceType}

        for technology in TechnologyType:
            assert set(technology.base_cost) <= known, technology.name

    def test_the_first_level_costs_exactly_the_base_price(self):
        """
        Le prix de base est celui du premier niveau, pas une reference abstraite.
        ---
        L'equation est `base x 2^(n-1)` : c'est ce qui permet de lire la table
        comme le cout d'entree dans une branche de recherche.
        """
        for technology in TechnologyType:
            assert technology.price(level=1) == technology.base_cost

    def test_each_level_costs_twice_the_previous(self):
        for technology in TechnologyType:
            for level in range(1, 5):
                cheaper = technology.price(level)
                dearer = technology.price(level + 1)
                for resource, amount in cheaper.items():
                    assert dearer[resource] == pytest.approx(amount * 2), (
                        technology.name, resource)

    def test_a_price_covers_only_what_the_line_actually_needs(self):
        """
        Chaque branche a ses propres materiaux.
        ---
        Enumerer quatre cles fixes ne marche plus depuis que la distorsion
        demande du neutronium et l'atome de l'uranium : le prix suit la table.
        """
        assert 'neutronium' in TechnologyType.distorsion.price(level=1)
        assert 'neutronium' not in TechnologyType.computer.price(level=1)

    def test_research_takes_longer_at_each_level(self, stub):
        researcher = stub(faction=None)

        for technology in TechnologyType:
            for level in range(0, 5):
                assert technology.duration(level + 1, user=researcher) > \
                    technology.duration(level, user=researcher)

    def test_every_line_has_both_its_equations(self):
        """
        Une equation manquante rendrait None, et l'appel leverait a l'usage.
        """
        for technology in TechnologyType:
            for equation_type in EquationType:
                assert TechnologyEquations.get(
                    tech_type=technology, equation_type=equation_type) is not None

    def test_a_line_is_found_by_its_name(self):
        assert TechnologyType.get_by_name('atom') is TechnologyType.atom
        assert TechnologyType.get_by_name('telepathie') is None


class TestResearchDuration:

    def test_without_a_faction_the_equation_stands_alone(self, stub):
        plain = TechnologyEquations.get(
            tech_type=TechnologyType.computer, equation_type=EquationType.time)(3)

        assert TechnologyType.computer.duration(
            level=3, user=stub(faction=None)) == plain

    def test_a_technocrat_researches_faster(self, stub):
        """
        L'avantage de faction s'applique a la duree, pas au prix.
        ---
        C'est ce qui distingue une faction de chercheurs d'une faction riche :
        elle ne paie pas moins, elle attend moins.
        """
        faction = a_faction((
            FactionAdvantageType.TimeReduce,
            FactionAdvantageScope.Technologies,
            {'percentage': -10},
        ))
        plain = TechnologyType.computer.duration(
            level=3, user=stub(faction=None))

        assert TechnologyType.computer.duration(
            level=3, user=stub(faction=faction)) == pytest.approx(plain * 0.9)


class TestTechnology:

    def make(self, level=0, faction=None):
        technology = Technology(type=TechnologyType.computer, user_id=1, level=level)
        technology.user = User(username="chercheuse", email="c@testing.com")
        technology.user.faction = faction
        return technology

    def test_a_line_within_reach_can_be_researched(self, make_territory):
        territory = make_territory()
        technology = self.make(level=0)
        price = TechnologyType.computer.price(level=1)

        for resource, amount in price.items():
            if amount:
                setattr(territory, resource, amount)

        assert technology.can_be_increased(territory=territory)

    def test_a_line_out_of_reach_cannot(self, make_territory):
        territory = make_territory(silicium=0)
        technology = self.make(level=0)

        assert not technology.can_be_increased(territory=territory)

    def test_a_granted_level_costs_nothing(self, make_territory):
        """
        `now` monte le niveau sans rien facturer.
        ---
        C'est une faveur -- une avance de partie, un avantage de faction -- pas
        un achat. La recherche lancee par le joueur passe par l'autre branche et
        se paie a la commande, comme un batiment.
        """
        territory = make_territory()
        technology = self.make(level=2)
        reserves = dict(territory.resources)

        technology.increase(territory=territory, now=True)

        assert technology.level == 3
        assert territory.resources == reserves

    def test_what_the_client_reads_of_a_line(self):
        technology = self.researched(level=4)

        serialized = technology.serialize

        assert serialized['level'] == 4
        assert serialized['duration'] == TechnologyType.optical.duration(
            level=4, user=technology.user)
        assert serialized['created_at'] == MOMENT.isoformat()

    def researched(self, level=4, updated=None):
        technology = Technology(
            type=TechnologyType.optical, user_id=1, level=level,
            created_at=MOMENT, updated_at=updated or MOMENT)
        technology.user = User(username="chercheuse", email="c@testing.com")
        return technology


class TestKnownSerializationDefects:
    """
    Deux defauts constates, ecrits comme ils devraient l'etre.

    `xfail(strict=True)` dit exactement cela : le test decrit ce qu'on attend,
    il echoue aujourd'hui, et il se signalera le jour ou il passera -- a charge
    alors de retirer la marque. C'est preferable a un test qui enterine le
    defaut, lequel rendrait la correction plus difficile qu'aujourd'hui.

    Aucun des deux ne se voit dans les tests d'API existants : ils ne lisent pas
    ces champs-la.
    """

    def a_technology(self, updated_at=None):
        technology = Technology(
            type=TechnologyType.optical, user_id=1, level=4,
            created_at=MOMENT, updated_at=updated_at or MOMENT)
        technology.user = User(username="chercheuse", email="c@testing.com")
        return technology

    @pytest.mark.xfail(strict=True, reason=(
        "TechnologyType n'a pas de __str__ : le champ vaut "
        "'TechnologyType.optical'. Les trois autres enums serialises de la "
        "sorte -- ResourceType, PositionalEventType, BuildingType -- l'ont "
        "recu pour cette raison precise."))
    def test_a_line_is_named_as_the_api_expects_to_receive_it(self):
        """
        Le nom serialise doit etre celui qu'on peut renvoyer.
        ---
        `POST /api/technology/<name>/<territory>` resout le nom par
        `TechnologyType.get_by_name`, qui attend 'optical'. La lecture en rend
        'TechnologyType.optical' : le client ne peut pas reposter ce qu'il a
        lu sans retirer le prefixe a la main.
        """
        assert self.a_technology().serialize['type'] == 'optical'

    @pytest.mark.xfail(strict=True, reason=(
        "'updated_at' recopie created_at (technology.py:141). Meme erreur dans "
        "User.serialize et Role.serialize."))
    def test_the_update_date_is_the_update_date(self):
        """
        Deux dates identiques rendent la seconde inutile.
        ---
        C'est la date qui dit quand un niveau a ete atteint : recopier celle de
        creation la fige au premier jour de la partie.
        """
        later = MOMENT + timedelta(days=3)

        assert self.a_technology(
            updated_at=later).serialize['updated_at'] == later.isoformat()
