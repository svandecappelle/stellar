# -*- coding: utf-8 -*-

"""
Vivres, population et stabilite : la boucle de vie d'une colonie.

Trois grandeurs qui n'en font qu'une :

    la ferme remplit la reserve  ->  la population mange  ->  rassasiee elle
    croit et le monde s'apaise, affamee elle stagne et la stabilite descend, ce
    qui fait baisser toute la production du territoire.

La boucle est jouee a la lecture, sur les heures ecoulees depuis la derniere
vue du monde. C'est ce qui la rend difficile a observer en jeu -- il faut
attendre -- et facile a lire ici : on l'appelle avec le nombre d'heures qu'on
veut.

Ces tests appellent `_run_life_cycle` et `_grow_population` directement. Ce sont
des methodes privees, mais elles portent une regle du jeu entiere ; les
atteindre par `update_view` demanderait une base, des evenements et une horloge,
pour verifier moins de choses.

Deux garde-fous ont ici plus de valeur que les formules elles-memes :

  · la famine ne tue personne. Elle se paie en stabilite, jamais en habitants --
    une population qui fond ferait fondre la recolte, et le monde ne pourrait
    plus jamais remonter ;
  · un monde vide est stable. Sans bouche a nourrir il n'y a pas de disette, et
    une planete tombee a zero habitant doit pouvoir repartir.
"""

import pytest

from app.models.game.buildings import BuildingType
from app.models.game.planet import PlanetArchetype
from app.models.game.territory import (
    FOOD_PER_POPULATION_HOUR, POPULATION_GROWTH_RATE, POPULATION_SEED,
    STABILITY_DECAY_HOUR, STABILITY_FLOOR_FACTOR, STABILITY_MAX,
    STABILITY_RECOVERY_HOUR, ResourceType)


class TestUpkeep:

    def test_the_population_eats_by_the_head(self, make_territory):
        territory = make_territory(population=100)

        assert territory.food_upkeep == pytest.approx(
            100 * FOOD_PER_POPULATION_HOUR)

    def test_an_empty_world_eats_nothing(self, make_territory):
        assert make_territory(population=0).food_upkeep == 0

    def test_the_balance_weighs_the_harvest_against_the_mouths(
            self, make_territory):
        """
        Ce que le client affiche a cote de la reserve.
        ---
        Sans lui le joueur verrait une recolte brute et ne comprendrait pas
        pourquoi son stock fond.
        """
        territory = make_territory(population=100)
        harvest = territory.get_hourly_gain(resource_type=ResourceType.food)

        assert territory.food_balance == pytest.approx(
            harvest - territory.food_upkeep)

    def test_a_world_without_an_owner_has_no_balance(self, make_territory):
        """
        La production depend du joueur, sa faction notamment : un monde
        inhabite n'en a pas, et ne se calcule pas.
        """
        territory = make_territory(population=100)
        territory.user_id = None

        assert territory.food_balance == 0.0
        assert territory.population_capacity == 0


class TestCapacity:

    def test_the_limit_is_what_the_farms_can_feed(self, make_territory):
        """
        Pas un chiffre pose a la main : exactement ce que la recolte nourrit.
        ---
        Construire une ferme est donc la seule facon de faire monter une
        population, et une planete sterile n'en portera jamais beaucoup.
        """
        territory = make_territory()
        harvest = territory.get_hourly_gain(resource_type=ResourceType.food)

        assert territory.population_capacity == int(
            harvest / FOOD_PER_POPULATION_HOUR
            * territory.planet_archetype.habitability_factor)

    def test_a_farm_raises_the_ceiling(self, make_territory):
        territory = make_territory()
        before = territory.population_capacity

        territory.get_building(BuildingType.farm).level = 3

        assert territory.population_capacity > before

    def test_habitability_counts_twice_and_on_purpose(self, make_territory):
        """
        L'habitabilite joue sur la recolte, puis sur ce qu'elle fait vivre.
        ---
        C'est voulu. Sans la seconde fois, un monde accueillant ne serait qu'un
        monde qui recolte un peu plus, et l'ecart entre une planete temperee et
        un caillou irradie ne se verrait pas -- or c'est precisement ce que le
        joueur choisit quand il colonise.
        """
        temperate = make_territory(archetype=PlanetArchetype.oceanic)
        harsh = make_territory(archetype=PlanetArchetype.irradiated)
        # Des fermes montees : la capacite est un entier tronque, et sur les
        # petits nombres du niveau zero l'arrondi pese plus que la regle qu'on
        # mesure.
        for territory in (temperate, harsh):
            territory.get_building(BuildingType.farm).level = 5

        factor = (PlanetArchetype.oceanic.habitability_factor
                  / PlanetArchetype.irradiated.habitability_factor)

        assert temperate.population_capacity == pytest.approx(
            harsh.population_capacity * factor ** 2, rel=0.01)


class TestEating:

    def test_a_fed_world_grows_and_calms_down(self, make_territory):
        territory = make_territory(population=100, food=1000, stability=50)
        capacity = territory.population_capacity

        territory._run_life_cycle(hours=2)

        assert territory.food == pytest.approx(1000 - 100 * FOOD_PER_POPULATION_HOUR * 2)
        assert territory.population > 100
        assert territory.population < capacity
        assert territory.stability == pytest.approx(50 + STABILITY_RECOVERY_HOUR * 2)

    def test_a_starving_world_keeps_its_people_and_loses_its_temper(
            self, make_territory):
        """
        La famine se paie en stabilite, jamais en habitants.
        ---
        Faire mourir la population ferait tomber la recolte avec elle : le monde
        entrerait dans une spirale dont rien ne pourrait le sortir. Un monde
        affame reste peuple, il devient seulement ingouvernable.
        """
        territory = make_territory(population=100, food=0, stability=STABILITY_MAX)

        territory._run_life_cycle(hours=1)

        assert territory.population == 100
        assert territory.food == 0
        assert territory.stability == pytest.approx(
            STABILITY_MAX - STABILITY_DECAY_HOUR)

    def test_a_half_fed_world_pays_half_the_price(self, make_territory):
        """
        La perte suit la severite de la disette.
        ---
        Une reserve qui couvre les trois quarts des besoins ne coute qu'un quart
        de la penalite : un joueur qui redresse a moitie voit son effort compter.
        """
        territory = make_territory(population=100, food=2, stability=STABILITY_MAX)
        needed = territory.food_upkeep  # 5 pour cent habitants

        territory._run_life_cycle(hours=1)

        fed = 2 / needed
        assert territory.food == 0
        assert territory.stability == pytest.approx(
            STABILITY_MAX - STABILITY_DECAY_HOUR * (1 - fed))

    def test_an_empty_world_is_perfectly_stable(self, make_territory):
        """
        Sans bouche a nourrir il n'y a pas de famine.
        ---
        Un monde vide n'est pas un monde affame : il n'est simplement pas
        peuple. Le confondre condamnerait toute planete repeuplee a zero.
        """
        territory = make_territory(population=0, food=0, stability=10)

        territory._run_life_cycle(hours=1)

        assert territory.stability == pytest.approx(10 + STABILITY_RECOVERY_HOUR)
        assert territory.population > 0

    def test_stability_never_leaves_its_range(self, make_territory):
        calm = make_territory(population=10, food=1000, stability=STABILITY_MAX)
        calm._run_life_cycle(hours=100)
        assert calm.stability == STABILITY_MAX

        furious = make_territory(population=100, food=0, stability=1)
        furious._run_life_cycle(hours=100)
        assert furious.stability == 0

    def test_a_tour_of_no_duration_changes_nothing(self, make_territory):
        """
        Deux lectures a la suite ne doivent pas faire manger deux fois.
        ---
        L'etat se rattrape a la lecture : rafraichir une page ferait passer un
        tour a chaque fois si la duree nulle n'etait pas ecartee.
        """
        territory = make_territory(population=100, food=500, stability=42)

        territory._run_life_cycle(hours=0)

        assert (territory.food, territory.population, territory.stability) == (
            500, 100, 42)

    def test_fractions_of_an_hour_are_not_rounded_away(self, make_territory):
        """
        La reserve garde ses decimales entre deux ecritures.
        ---
        C'est la colonne entiere qui tronque a l'enregistrement. Arrondir ici
        ferait disparaitre la consommation d'un tour trop court, et un joueur
        qui rafraichit souvent ne mangerait jamais.
        """
        territory = make_territory(population=10, food=100)

        territory._run_life_cycle(hours=0.5)

        assert territory.food == pytest.approx(
            100 - 10 * FOOD_PER_POPULATION_HOUR * 0.5)


class TestGrowth:

    def test_growth_is_fastest_in_the_middle_and_dies_at_the_limit(
            self, make_territory):
        """
        Croissance logistique : une cloche, pas une pente.
        ---
        Elle est lente sur un monde presque vide -- peu de monde pour faire des
        enfants -- lente sur un monde plein -- plus de place -- et maximale a
        mi-capacite. C'est ce qui fait qu'une colonie demarre doucement puis
        s'emballe, au lieu de croitre d'autant plus vite qu'elle est petite.
        """
        territory = make_territory(food=100000)
        capacity = territory.population_capacity

        def growth_at(share):
            territory.population = int(capacity * share)
            territory._grow_population(hours=1)
            return territory.population - int(capacity * share)

        assert growth_at(0.5) > growth_at(0.1) > 0
        assert growth_at(0.5) > growth_at(0.9) > 0

    def test_a_full_world_stops_growing(self, make_territory):
        territory = make_territory()
        territory.population = territory.population_capacity

        territory._grow_population(hours=10)

        assert territory.population == territory.population_capacity

    def test_growth_never_overshoots_the_limit(self, make_territory):
        territory = make_territory()
        capacity = territory.population_capacity
        territory.population = capacity - 1

        territory._grow_population(hours=1000)

        assert territory.population == capacity

    def test_a_world_emptied_of_its_people_can_start_again(self, make_territory):
        """
        Zero fois deux pour cent vaut zero : il faut un plancher.
        ---
        Sans lui une planete tombee a zero habitant resterait morte pour
        toujours, quelle que soit la recolte.
        """
        territory = make_territory(population=0)
        capacity = territory.population_capacity

        territory._grow_population(hours=1)

        assert territory.population == pytest.approx(
            POPULATION_GROWTH_RATE * POPULATION_SEED * (1.0 - 0 / capacity))

    def test_a_sterile_world_carries_nobody(self, make_territory):
        """
        Aucune recolte, aucune capacite, aucune croissance.
        ---
        Le cas se rencontre : une geante gazeuse ne nourrit personne. Il ne doit
        pas se solder par une division par zero a chaque lecture du monde.
        """
        territory = make_territory(archetype=PlanetArchetype.gas_giant)
        territory.get_building(BuildingType.farm).level = 0
        # La ferme rend un fond meme au niveau zero : on la neutralise pour
        # obtenir un monde reellement sterile.
        territory.buildings = [b for b in territory.buildings
                               if b.type is not BuildingType.farm]

        assert territory.population_capacity == 0

        territory.population = 100
        territory._grow_population(hours=5)
        assert territory.population == 100

    def test_the_growth_announced_matches_the_next_hour(self, make_territory):
        """
        Le client ne doit pas promettre une croissance que le tour ne rendra pas.
        ---
        Deux formules pour la meme chose, l'une affichee et l'autre appliquee :
        elles doivent donner le meme nombre sur une heure.
        """
        territory = make_territory(population=200, food=10000)
        announced = territory.population_growth

        territory._run_life_cycle(hours=1)

        assert territory.population - 200 == pytest.approx(announced)

    def test_nothing_is_promised_to_a_starving_world(self, make_territory):
        territory = make_territory(population=200, food=0)
        territory.get_building(BuildingType.farm).level = 0
        territory.buildings = [b for b in territory.buildings
                               if b.type is not BuildingType.farm]

        assert territory.is_starving
        assert territory.population_growth == 0.0


class TestStarvation:

    def test_starving_is_an_empty_reserve_and_a_negative_balance(
            self, make_territory):
        """
        Les deux conditions, pas une seule.
        ---
        Une reserve vide sur un monde qui recolte assez n'est pas une famine :
        c'est un stock a zero qui se remplit. Confondre les deux ferait clignoter
        l'alerte en permanence sur un monde qui va bien.
        """
        territory = make_territory(population=10, food=0)
        assert territory.food_balance > 0
        assert not territory.is_starving

        territory.population = 100000
        assert territory.food_balance < 0
        assert territory.is_starving

    def test_a_full_reserve_is_never_a_famine(self, make_territory):
        territory = make_territory(population=100000, food=500)

        assert territory.food_balance < 0
        assert not territory.is_starving


class TestStabilityReadings:

    def test_the_displayed_score_is_a_whole_number_within_bounds(
            self, make_territory):
        """
        La colonne porte un flottant entre deux ecritures.
        ---
        Le tour de jeu y ajoute des fractions d'heure ; un client qui attend un
        entier ne saurait pas quoi en faire.
        """
        assert make_territory(stability=73.6).stability_score == 73
        assert make_territory(stability=-5).stability_score == 0
        assert make_territory(stability=250).stability_score == STABILITY_MAX
        assert make_territory(stability=None).stability_score == STABILITY_MAX

    def test_a_calm_world_produces_exactly_what_it_always_did(
            self, make_territory):
        """
        A 100, le facteur vaut 1 : les territoires deja en jeu ne perdent rien.
        ---
        C'est la condition pour que la stabilite ait pu etre ajoutee a une
        partie en cours sans rien retirer a personne.
        """
        assert make_territory(stability=STABILITY_MAX).stability_factor == 1.0

    def test_even_an_ungovernable_world_keeps_working(self, make_territory):
        assert make_territory(stability=0).stability_factor == pytest.approx(
            STABILITY_FLOOR_FACTOR)

    def test_the_factor_follows_the_score(self, make_territory):
        assert make_territory(stability=50).stability_factor == pytest.approx(
            STABILITY_FLOOR_FACTOR + (1 - STABILITY_FLOOR_FACTOR) * 0.5)


class TestSpending:

    def test_a_cost_is_taken_out_of_the_reserves(self, make_territory):
        territory = make_territory(iron=1000, credits=500)

        territory.spend({'iron': 300, 'credits': 100})

        assert territory.iron == 700
        assert territory.credits == 400

    def test_a_cost_is_read_by_name_or_by_type(self, make_territory):
        """
        Les deux ecritures se rencontrent selon d'ou vient le cout.
        ---
        Une table de batiment donne des `ResourceType`, un cout de vaisseau des
        chaines : `spend` est appele par les deux chemins.
        """
        territory = make_territory(iron=1000)

        territory.spend({ResourceType.iron: 100})
        territory.spend({'iron': 100})

        assert territory.iron == 800

    def test_energy_and_population_are_asked_for_but_never_burnt(
            self, make_territory):
        """
        Deux ressources qu'un cout exige sans les consommer.
        ---
        L'energie n'est pas un stock mais un solde, recalcule a chaque lecture :
        la debiter n'aurait aucun effet durable. La population sert les batteries
        et arme les vaisseaux, elle n'est pas brulee -- la debiter deperait la
        colonie a chaque chantier, sans rien qui la rende.
        """
        territory = make_territory(population=100)
        before = territory.energy

        territory.spend({'energy': 50, 'population': 20})

        assert territory.population == 100
        assert territory.energy == before

    def test_a_free_line_is_skipped(self, make_territory):
        territory = make_territory(iron=1000)

        territory.spend({'iron': 0, 'cristal': None})

        assert territory.iron == 1000


class TestPrerequisites:

    def test_a_cost_within_reach_is_accepted(self, make_territory):
        territory = make_territory(iron=1000, credits=500)

        assert territory.match_prerequisite({'iron': 1000, 'credits': 499})

    def test_a_single_resource_short_is_enough_to_refuse(self, make_territory):
        """
        Tout le cout, ou rien : on ne construit pas a credit.
        """
        territory = make_territory(iron=1000, credits=500)

        assert not territory.match_prerequisite({'iron': 1000, 'credits': 501})

    def test_energy_is_compared_against_the_balance_not_a_stock(
            self, make_territory):
        """
        L'energie que le prerequis regarde est celle qui reste disponible.
        ---
        Elle n'a pas de colonne : c'est ce que la centrale produit moins ce que
        les batiments consomment. Un batiment de plus doit tenir dans ce solde.
        """
        territory = make_territory()
        available = territory.energy

        assert territory.match_prerequisite({'energy': available})
        assert not territory.match_prerequisite({'energy': available + 1})
