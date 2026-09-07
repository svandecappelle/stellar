# -*- coding: utf-8 -*-

"""
Le voyage d'une flotte, sans horloge de jeu et sans base.

Il n'y a pas de boucle de jeu derriere un deplacement : une flotte avance quand
on la lit, comme un territoire produit quand on le regarde. Tout se joue donc
sur deux choses -- l'heure qu'il est, et le chemin fige au depart -- et les deux
se posent a la main. C'est ce qui permet de traverser une galaxie en trois
lignes ici, la ou `tests/api/game/travel.py` doit monter une base, un joueur et
des requetes pour le meme trajet.

Ce niveau-ci sert a autre chose que le sien : il regarde les etats intermediaires
qu'une reponse HTTP ne montre pas. Ou est la flotte a la moitie d'un saut, ce
que devient sa position en arrivant, ce qu'un ordre donne en plein vol laisse du
precedent.

Une regle domine tout le reste : une flotte appartient toujours a un systeme.
Entre deux etoiles, c'est celle qu'elle vient de quitter. Le serveur doit
pouvoir repondre « dans lequel ? » a tout instant, et un point du vide n'est pas
une reponse.
"""

import datetime
import json

import pytest
from freezegun import freeze_time

from app.models.game import starlanes
from app.models.game.fleet import Fleet, TRAVEL_SECONDS_PER_UNIT
from app.models.game.ship import Ship, ShipType


#: La meme chaine d'etoiles que pour le graphe des liaisons : deux bouts a huit
#: unites l'un de l'autre, donc hors de portee directe, et deux etoiles basses
#: qui evitent aux extremites d'elargir leur recherche jusqu'a se rejoindre.
#:
#:   HOME ---4--- RELAY ---4--- FAR
#:    |                          |
#:   HOME2                      FAR2
CHAIN = ["0_0_0", "0_3_0", "4_0_0", "8_0_0", "8_3_0"]
HOME, HOME2, RELAY, FAR, FAR2 = range(1, 6)

#: Un amas hors d'atteinte du precedent.
ELSEWHERE = ["100_0_0", "104_0_0", "102_3_0"]
EXILE = 6


@pytest.fixture(name="fleet")
def fleet():
    """Une flotte a quai dans le systeme d'origine."""
    return Fleet(system_id=HOME, user_id=1, name="Premiere")


@pytest.fixture(name="departure")
def departure():
    """Une heure fixe : le voyage se lit a l'horloge, elle ne doit pas bouger."""
    return datetime.datetime(2026, 1, 1, 12, 0, 0)


class TestPosition:

    def test_a_new_fleet_sits_at_the_origin(self, fleet):
        """
        Le plan orbital est en y=0 : une flotte sans position s'y trouve.
        ---
        Ce sont des coordonnees Unity, dans le repere du systeme. Le serveur ne
        les calcule pas et ne les interprete pas ; il les garde pour que la
        flotte se retrouve au meme endroit a la prochaine entree.
        """
        assert fleet.position == {'x': 0.0, 'y': 0.0, 'z': 0.0}

    def test_a_client_places_its_fleet_where_it_wants(self, fleet):
        fleet.move_to({'x': 1.5, 'y': -2, 'z': 3})

        assert fleet.position == {'x': 1.5, 'y': -2.0, 'z': 3.0}

    def test_a_client_without_geometry_leaves_the_fleet_alone(self, fleet):
        """
        Un `None` ne deplace rien.
        ---
        C'est ce qu'envoie un client sans geometrie -- la console web notamment,
        qui manoeuvre les flottes sans jamais savoir ou elles sont a l'ecran.
        Prendre son silence pour l'origine les ramenerait toutes au centre du
        systeme a chaque ordre.
        """
        fleet.move_to({'x': 4, 'y': 0, 'z': 5})
        fleet.move_to(None)

        assert fleet.position == {'x': 4.0, 'y': 0.0, 'z': 5.0}

    def test_an_axis_left_out_keeps_its_value(self, fleet):
        fleet.move_to({'x': 4, 'y': 1, 'z': 5})
        fleet.move_to({'x': 9})

        assert fleet.position == {'x': 9.0, 'y': 1.0, 'z': 5.0}

    def test_an_orbit_is_declared_and_dropped(self, fleet):
        """
        L'orbite est declaree, jamais deduite.
        ---
        Le serveur ne connait aucune coordonnee de planete : il ne pourrait pas
        deviner une orbite d'une distance. Et c'est pourtant sur elle que se
        decide l'affectation d'un vaisseau qui sort de chantier.
        """
        fleet.set_orbit(42)
        assert fleet.orbiting_territory_id == 42

        fleet.set_orbit(None)
        assert fleet.orbiting_territory_id is None


class TestComposition:

    def test_a_fleet_counts_what_it_carries(self, fleet):
        fleet.ships.append(Ship(fleet_id=1, type=ShipType.Fighter, count=3))
        fleet.ships.append(Ship(fleet_id=1, type=ShipType.Cruiser, count=2))

        assert fleet.composition == {'Fighter': 3, 'Cruiser': 2}
        assert fleet.size == 5
        assert not fleet.is_empty

    def test_an_emptied_line_is_not_reported(self, fleet):
        """
        Une ligne tombee a zero disparait de la composition.
        ---
        Le client dessine ce qu'il recoit : une ligne a zero lui ferait afficher
        un type de vaisseau que la flotte n'a plus.
        """
        fleet.ships.append(Ship(fleet_id=1, type=ShipType.Fighter, count=0))

        assert fleet.composition == {}
        assert fleet.size == 0
        assert fleet.is_empty


class TestDeparture:

    def test_a_route_is_frozen_at_departure(self, fleet, place, departure):
        """
        Le chemin et la duree de chaque saut sont fixes au moment du depart.
        ---
        Les recalculer a chaque lecture ferait changer une route sous les pieds
        du joueur si la galaxie s'agrandissait en cours de partie -- et une
        heure d'arrivee annoncee cesserait d'etre une promesse.
        """
        place(CHAIN)

        with freeze_time(departure):
            route = fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        assert route == [HOME, RELAY, FAR]
        assert fleet.route == route
        assert fleet.is_travelling
        assert fleet.travel_started_at == departure

    def test_the_flight_time_is_paid_by_the_distance(self, fleet, place):
        """
        Sans cela la topologie ne servirait a rien : un detour de trois sauts
        courts couterait le meme prix qu'un saut long.
        """
        place(CHAIN)
        fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        lengths = starlanes.leg_lengths("chain", [HOME, RELAY, FAR])
        assert fleet.legs == pytest.approx(
            [length * TRAVEL_SECONDS_PER_UNIT for length in lengths])

    def test_the_galaxy_can_be_made_faster(self, fleet, place, tune):
        tune(fleet_speed_multiplier=4.0)
        place(CHAIN)

        fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        lengths = starlanes.leg_lengths("chain", [HOME, RELAY, FAR])
        assert fleet.legs == pytest.approx(
            [length * TRAVEL_SECONDS_PER_UNIT / 4.0 for length in lengths])

    def test_leaving_means_leaving_the_orbit(self, fleet, place):
        """
        Partir, c'est quitter l'orbite.
        ---
        Autrement le chantier reste derriere continuerait de lui livrer ses
        vaisseaux a l'autre bout de la galaxie : c'est `orbiting_territory_id`
        qui decide de l'affectation.
        """
        place(CHAIN)
        fleet.set_orbit(7)

        fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        assert fleet.orbiting_territory_id is None

    def test_an_unreachable_destination_leaves_the_fleet_where_it_is(
            self, fleet, place):
        """
        Aucune suite de liaisons, aucun voyage -- et rien d'entame.
        ---
        Une galaxie peut avoir des amas isoles. Le refus doit etre net : une
        flotte a demi partie, avec une route posee et pas de destination
        atteignable, ne saurait plus ou elle est.
        """
        place(CHAIN + ELSEWHERE)

        assert fleet.travel_to(destination_id=EXILE, galaxy_name="split") is None
        assert not fleet.is_travelling
        assert fleet.system_id == HOME

    def test_going_where_one_already_is_is_not_a_voyage(self, fleet, place):
        place(CHAIN)

        assert fleet.travel_to(destination_id=HOME, galaxy_name="chain") is None
        assert not fleet.is_travelling


class TestInFlight:

    def travelling(self, fleet, departure):
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")
        return fleet

    def test_a_fleet_belongs_to_the_last_relay_it_passed(
            self, fleet, place, departure):
        """
        Entre deux etoiles, c'est celle qu'elle vient de quitter.
        ---
        Le client sait la placer sur le trait grace a `travel` ; il fallait au
        serveur une reponse simple a « dans quel systeme ? », et un point du
        vide n'en est pas une.
        """
        place(CHAIN)
        self.travelling(fleet, departure)
        legs = fleet.legs

        # Au milieu du premier saut : partie de HOME, pas encore a RELAY.
        with freeze_time(departure + datetime.timedelta(seconds=legs[0] / 2)):
            fleet.refresh()
            assert fleet.system_id == HOME

        # Au milieu du second : elle a quitte RELAY.
        with freeze_time(departure + datetime.timedelta(
                seconds=legs[0] + legs[1] / 2)):
            fleet.refresh()
            assert fleet.system_id == RELAY
            assert fleet.is_travelling

    def test_the_client_is_told_which_leg_and_how_far_along(
            self, fleet, place, departure):
        """
        Le serveur ne sait pas placer une flotte sur la carte.
        ---
        Il n'a pas l'echelle a laquelle Unity dessine la galaxie. Il donne donc
        les deux etoiles du saut en cours et la fraction parcourue entre elles :
        c'est au client d'en tirer un point.
        """
        place(CHAIN)
        self.travelling(fleet, departure)
        legs = fleet.legs

        with freeze_time(departure + datetime.timedelta(
                seconds=legs[0] + legs[1] / 4)):
            travel = fleet.travel

        assert travel['from_id'] == RELAY
        assert travel['to_id'] == FAR
        assert travel['destination_id'] == FAR
        assert travel['leg_index'] == 1
        assert travel['leg_progress'] == pytest.approx(0.25)
        assert travel['seconds_left'] == pytest.approx(legs[1] * 0.75)

    def test_the_client_is_given_the_legs_to_animate_on_its_own(
            self, fleet, place, departure):
        """
        La duree de chaque saut voyage avec l'etat.
        ---
        Sans elle le client devrait interroger le serveur a chaque image pour
        faire avancer la flotte, ou la laisser sauter d'un relais a l'autre.
        """
        place(CHAIN)
        self.travelling(fleet, departure)

        with freeze_time(departure):
            travel = fleet.travel

        assert travel['legs'] == fleet.legs
        assert travel['started_at'] == departure.isoformat()
        assert travel['arriving_at'] == (
            departure + datetime.timedelta(seconds=sum(fleet.legs))).isoformat()

    def test_a_fleet_at_anchor_has_no_voyage_to_report(self, fleet):
        assert fleet.travel is None
        assert fleet.route == []
        assert fleet.legs == []
        assert fleet.refresh() is False


class TestArrival:

    def test_arriving_ends_the_voyage(self, fleet, place, departure):
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        with freeze_time(departure + datetime.timedelta(
                seconds=sum(fleet.legs) + 1)):
            assert fleet.refresh() is True

        assert fleet.system_id == FAR
        assert not fleet.is_travelling
        assert fleet.travel is None

    def test_an_arriving_fleet_appears_at_the_centre_without_an_orbit(
            self, fleet, place, departure):
        """
        Elle arrive dans l'espace du systeme, a l'origine du repere.
        ---
        Garder la position qu'elle avait dans un autre systeme la ferait
        apparaitre au hasard de la geometrie de celui-ci -- dans une etoile,
        peut-etre. Le client la posera ou il l'entend a la premiere manoeuvre.
        """
        place(CHAIN)
        fleet.move_to({'x': 12, 'y': 3, 'z': -4})
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        with freeze_time(departure + datetime.timedelta(
                seconds=sum(fleet.legs) + 1)):
            fleet.refresh()

        assert fleet.position == {'x': 0.0, 'y': 0.0, 'z': 0.0}
        assert fleet.orbiting_territory_id is None


class TestOrdersGivenInFlight:

    def test_a_new_order_finishes_the_current_leg(self, fleet, place, departure):
        """
        Un ordre donne en vol ne fait pas demi-tour dans le vide.
        ---
        On ne circule que par les liaisons : la flotte finit le saut commence,
        et le nouveau chemin part du relais qu'elle atteint. C'est aussi ce qui
        empeche un ordre repete a chaque seconde de faire surplace, chaque ordre
        repartant sinon du meme point.
        """
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")
        first_leg = fleet.legs[0]

        # A mi-chemin de RELAY, on la renvoie chez elle.
        with freeze_time(departure + datetime.timedelta(seconds=first_leg / 2)):
            route = fleet.travel_to(destination_id=HOME, galaxy_name="chain")

        assert route[:2] == [HOME, RELAY]
        assert route[-1] == HOME
        # Il ne reste que la moitie du saut engage.
        assert fleet.legs[0] == pytest.approx(first_leg / 2)

    def test_an_order_repeated_does_not_keep_the_fleet_in_place(
            self, fleet, place, departure):
        """
        Le meme ordre donne deux fois avance quand meme.
        ---
        Si chaque ordre repartait du systeme de depart, un client qui redemande
        la meme destination a chaque image annulerait le trajet en continu.
        """
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")
        total = sum(fleet.legs)

        midway = departure + datetime.timedelta(seconds=fleet.legs[0] / 2)
        with freeze_time(midway):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")

            assert fleet.route == [HOME, RELAY, FAR]
            assert sum(fleet.legs) == pytest.approx(total - fleet.legs[0])


class TestInterruption:

    def test_stopping_puts_the_fleet_at_the_last_relay(
            self, fleet, place, departure):
        """
        Interrompre un voyage pose la flotte au dernier relais franchi.
        ---
        Et non la ou elle se trouve : entre deux etoiles elle ne serait dans
        aucun systeme, ce que le modele ne sait pas dire.
        """
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")
        legs = fleet.legs

        with freeze_time(departure + datetime.timedelta(
                seconds=legs[0] + legs[1] / 2)):
            assert fleet.stop_travel() is True

        assert fleet.system_id == RELAY
        assert not fleet.is_travelling

    def test_a_fleet_at_anchor_has_nothing_to_interrupt(self, fleet):
        assert fleet.stop_travel() is False

    def test_stopping_after_arrival_simply_confirms_it(
            self, fleet, place, departure):
        """
        Un ordre d'arret arrive apres coup ne ramene pas la flotte en arriere.
        ---
        Le rattrapage est paresseux : la flotte peut etre arrivee sans que
        personne ne l'ait encore lue. L'arret doit constater l'arrivee, pas la
        defaire.
        """
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        with freeze_time(departure + datetime.timedelta(
                seconds=sum(fleet.legs) + 10)):
            assert fleet.stop_travel() is True

        assert fleet.system_id == FAR


class TestStoredRoute:

    def test_the_route_survives_as_plain_json(self, fleet, place, departure):
        """
        Trois colonnes plutot qu'une table de trajets.
        ---
        Une flotte n'a qu'un voyage a la fois, et il est fige au depart : la
        route et les durees tiennent dans deux colonnes de texte, relues telles
        quelles a la lecture suivante.
        """
        place(CHAIN)
        with freeze_time(departure):
            fleet.travel_to(destination_id=FAR, galaxy_name="chain")

        assert json.loads(fleet.travel_route) == [HOME, RELAY, FAR]
        assert json.loads(fleet.travel_legs) == fleet.legs
