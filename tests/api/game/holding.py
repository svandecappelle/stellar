# -*- coding: utf-8 -*-

"""
Tenir un monde : raccordement, isolement, secession, lignes de commerce.

Trois fils conducteurs :

  · **L'isolement se mesure en chemin jusqu'a la capitale.** Sous la regle « au
    moins une ligne », deux mondes perdus relies l'un a l'autre se declareraient
    tous deux raccordes. C'est la premiere chose eprouvee ici.

  · **A zero, le monde s'eteint ; il ne part qu'apres.** La fenetre existe pour
    qu'un joueur absent puisse rentrer. Et quand il part, il part avec TOUT :
    stock, batiments, population. La secession punit sans confisquer.

  · **Une colonie ne nait jamais isolee.** Le vaisseau qui la fonde est son
    premier convoi, sans quoi elle perdrait de la stabilite des la premiere
    heure — sans depot, et sans les ressources pour en batir un.
"""

from datetime import datetime, timedelta

import pytest

from app.models.game.buildings import BuildingType
from app.models.game.fleet import Fleet
from app.models.game.planet import PlanetArchetype
from app.models.game.ship import ShipType
from app.models.game.system import System
from app.models.game.territory import (
    SECESSION_DAYS, STABILITY_ISOLATION_HOUR, STABILITY_MAX, Territory)
from app.models.game.trade import THROUGHPUT_BASE, THROUGHPUT_PER_LEVEL, TradeLine


# ── Outillage ────────────────────────────────────────────────────────────────

def me(base_universe):
    return base_universe['users'][0]['model']


def capital(session, base_universe):
    """Le monde de depart de la fixture, tamponne capitale comme le fait la migration."""
    home = me(base_universe).territories[0]
    home.is_capital = True
    home.archetype = PlanetArchetype.telluric
    session.commit()
    return home


def outpost(session, base_universe, user, position="7_7_7", archetype=None):
    """Un monde tenu par le joueur, dans un systeme a lui seul."""
    system = System.create(galaxy=base_universe['galaxy'], position=position)
    session.commit()

    territory = system.territories[0]
    territory.archetype = archetype or PlanetArchetype.telluric
    territory.deposits = territory.archetype.roll_deposits()
    territory.assign(user=user)
    session.commit()
    return territory


def link(session, user, origin, destination, flows=None):
    line = TradeLine(user_id=user.id, origin_id=origin.id,
                     destination_id=destination.id, flows=flows or [])
    session.add(line)
    session.commit()
    return line


# ── Le raccordement ──────────────────────────────────────────────────────────

class TestReachingTheCapital:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_capital_is_connected_by_definition(self, session, base_universe):
        home = capital(session, base_universe)
        assert home.is_connected is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_lone_outpost_is_cut_off(self, session, base_universe):
        capital(session, base_universe)
        far = outpost(session, base_universe, me(base_universe))

        assert far.is_connected is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_line_to_the_capital_connects_it(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)

        link(session, user, home, far)
        assert far.is_connected is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_chain_carries(self, session, base_universe):
        """Deux sauts de ligne raccordent aussi bien qu'un."""
        user = me(base_universe)
        home = capital(session, base_universe)
        middle = outpost(session, base_universe, user, position="7_8_7")
        far = outpost(session, base_universe, user, position="7_9_7")

        link(session, user, home, middle)
        link(session, user, middle, far)

        assert far.is_connected is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_two_lost_worlds_linked_to_each_other_stay_lost(
            self, session, base_universe):
        """
        LE test de la regle. Sous « au moins une ligne active », ces deux mondes
        se declareraient raccordes alors qu'aucun chemin ne mene a la capitale.
        """
        user = me(base_universe)
        capital(session, base_universe)
        one = outpost(session, base_universe, user, position="8_1_8")
        two = outpost(session, base_universe, user, position="8_2_8")

        link(session, user, one, two)

        assert one.is_connected is False
        assert two.is_connected is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_system_does_not_cut_itself_off(self, session, base_universe):
        """
        Deux territoires d'un meme systeme sont raccordes sans ligne : c'est ce
        qui fait vivre une plateforme de la colonie d'a cote.
        """
        user = me(base_universe)
        home = capital(session, base_universe)

        neighbour = [t for t in home.system.territories if t.id != home.id]
        if not neighbour:
            pytest.skip("le systeme de depart n'a qu'un territoire")

        neighbour[0].assign(user=user)
        session.commit()

        assert neighbour[0].is_connected is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_closed_line_carries_nothing(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)

        line = link(session, user, home, far)
        assert far.is_connected is True

        line.close()
        session.commit()
        assert far.is_connected is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_hostile_fleet_at_one_end_cuts_the_line(self, session, base_universe):
        """
        Le blocus est un robinet, pas une demolition : la ligne reste ouverte.
        """
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        line = link(session, user, home, far)

        from app.models.user import User
        rival = User.new(username="rival", password="un-mot-de-passe",
                         email="rival@testing.com")
        session.commit()

        Fleet.create(system_id=far.system_id, user=rival, name="blocus")
        session.commit()

        assert line.is_blockaded is True
        assert line.is_open is True
        assert far.is_connected is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_world_without_an_owner_is_neither_connected_nor_isolated(
            self, session, base_universe):
        """Un monde en secession attend : il ne doit pas continuer a s'etioler."""
        free = outpost(session, base_universe, me(base_universe), position="6_6_6")
        free.user_id = None
        free.user = None
        session.commit()

        assert free.is_connected is True


# ── L'isolement ──────────────────────────────────────────────────────────────

class TestIsolationCosts:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_cut_off_world_loses_stability(self, session, base_universe):
        user = me(base_universe)
        capital(session, base_universe)
        far = outpost(session, base_universe, user)
        far.stability = STABILITY_MAX
        far.food = 10 ** 7
        session.commit()

        far._run_life_cycle(hours=10.0)

        assert far.stability_score == pytest.approx(
            STABILITY_MAX - STABILITY_ISOLATION_HOUR * 10, abs=1)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_connected_world_recovers(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far)

        far.stability = 50
        far.food = 10 ** 7
        session.commit()

        far._run_life_cycle(hours=10.0)
        assert far.stability_score > 50

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_famine_and_isolation_add_up(self, session, base_universe):
        """Un monde qu'on assiege ET qu'on affame tombe en une nuit."""
        user = me(base_universe)
        capital(session, base_universe)
        far = outpost(session, base_universe, user)
        far.stability = STABILITY_MAX
        far.food = 0
        far.population = 1000
        session.commit()

        far._run_life_cycle(hours=10.0)

        # Famine pleine (5/h) + isolement (1,5/h) : 65 points en dix heures.
        assert far.stability_score == pytest.approx(35, abs=2)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_isolation_alone_leaves_days_to_react(self, session, base_universe):
        """
        Soixante-sept heures jusqu'a l'extinction, plus trois jours de sursis :
        une absence de week-end ne coute pas un monde.
        """
        hours_to_zero = STABILITY_MAX / STABILITY_ISOLATION_HOUR
        assert hours_to_zero > 48
        assert hours_to_zero + SECESSION_DAYS * 24 > 5 * 24


# ── La secession ─────────────────────────────────────────────────────────────

class TestSecession:

    def dying(self, session, base_universe, days_ago):
        user = me(base_universe)
        capital(session, base_universe)
        far = outpost(session, base_universe, user)
        far.stability = 0
        far.unstable_since = datetime.utcnow() - timedelta(days=days_ago)
        far.food = 10 ** 7
        session.commit()
        return far

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_at_zero_it_is_only_deactivated(self, session, base_universe):
        far = self.dying(session, base_universe, days_ago=0)

        assert far.is_deactivated is True
        assert far._check_secession() is False
        assert far.user_id is not None

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_window_is_respected(self, session, base_universe):
        far = self.dying(session, base_universe, days_ago=SECESSION_DAYS - 1)

        assert far._check_secession() is False
        assert far.user_id is not None

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_past_the_window_it_goes(self, session, base_universe):
        far = self.dying(session, base_universe, days_ago=SECESSION_DAYS + 1)

        assert far._check_secession() is True
        assert far.user_id is None

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_leaves_with_everything(self, session, base_universe):
        """
        Le stock, les batiments, la population. Celui qui l'a laisse partir
        perd ce qu'il y avait entasse — mais peut tout recuperer en le
        reprenant.
        """
        far = self.dying(session, base_universe, days_ago=SECESSION_DAYS + 1)
        far.iron = 123456
        far.population = 777
        far.get_building(building_type=BuildingType.mater_extractor).level = 5
        session.commit()

        far._check_secession()

        assert far.user_id is None
        assert far.iron == 123456
        assert far.population == 777
        assert far.get_building(
            building_type=BuildingType.mater_extractor).level == 5

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_recovering_clears_the_countdown(self, session, base_universe):
        far = self.dying(session, base_universe, days_ago=1)
        far.stability = 40
        session.commit()

        assert far._check_secession() is False
        assert far.unstable_since is None

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_lines_that_led_there_are_closed(self, session, base_universe):
        user = me(base_universe)
        far = self.dying(session, base_universe, days_ago=SECESSION_DAYS + 1)
        line = link(session, user, user.territories[0], far)

        far._check_secession()

        assert line.is_open is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_losing_the_capital_promotes_another(self, session, base_universe):
        """
        Sans cela, tous les mondes restants se declareraient isoles et
        tomberaient l'un apres l'autre : perdre sa capitale couterait l'empire.
        """
        user = me(base_universe)
        home = capital(session, base_universe)
        other = outpost(session, base_universe, user)

        home.stability = 0
        home.unstable_since = datetime.utcnow() - timedelta(days=SECESSION_DAYS + 1)
        session.commit()

        home._check_secession()

        assert home.user_id is None
        assert Territory.get(id=other.id).is_capital is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_world_without_an_owner_does_not_secede_twice(
            self, session, base_universe):
        far = self.dying(session, base_universe, days_ago=SECESSION_DAYS + 1)
        far._check_secession()

        assert far._check_secession() is False


# ── Les lignes ───────────────────────────────────────────────────────────────

class TestTradeLines:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_throughput_follows_the_weaker_depot(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        line = link(session, user, home, far)

        home.get_building(building_type=BuildingType.depot).level = 4
        far.get_building(building_type=BuildingType.depot).level = 2
        session.commit()

        assert line.throughput == THROUGHPUT_BASE + THROUGHPUT_PER_LEVEL * 2

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_depot_at_zero_still_carries_something(self, session, base_universe):
        """Maigre, mais vivant : c'est ce qu'une colonie recoit le jour de sa fondation."""
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        line = link(session, user, home, far)

        assert line.throughput == THROUGHPUT_BASE
        assert line.throughput > 0

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_resources_flow_along_the_line(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'food', 'rate': 30.0, 'to_origin': False}])

        home.food = 5000
        far.food = 0
        session.commit()

        home._run_trade(hours=2.0)

        assert far.food == pytest.approx(60.0)
        assert home.food == pytest.approx(4940.0)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_flow_can_run_the_other_way(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'iron', 'rate': 25.0, 'to_origin': True}])

        home.iron = 0
        far.iron = 900
        session.commit()

        home._run_trade(hours=2.0)

        assert home.iron == pytest.approx(50.0)
        assert far.iron == pytest.approx(850.0)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_nothing_moves_beyond_the_throughput(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'iron', 'rate': 10 ** 6, 'to_origin': False}])

        home.iron = 10 ** 7
        far.iron = 0
        session.commit()

        home._run_trade(hours=1.0)

        assert far.iron == pytest.approx(THROUGHPUT_BASE)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_nothing_moves_that_is_not_there(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'cristal', 'rate': 100.0, 'to_origin': False}])

        home.cristal = 7
        far.cristal = 0
        session.commit()

        home._run_trade(hours=1.0)

        assert home.cristal == pytest.approx(0.0)
        assert far.cristal == pytest.approx(7.0)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_blockaded_line_carries_nothing(self, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'iron', 'rate': 10.0, 'to_origin': False}])

        from app.models.user import User
        rival = User.new(username="rival", password="un-mot-de-passe",
                         email="rival@testing.com")
        session.commit()
        Fleet.create(system_id=far.system_id, user=rival, name="blocus")
        session.commit()

        home.iron = 5000
        far.iron = 0
        session.commit()

        home._run_trade(hours=5.0)
        assert far.iron == 0

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_only_the_origin_runs_the_line(self, session, base_universe):
        """
        Les deux bouts se mettent a jour chacun de leur cote : une ligne jouee
        par les deux transporterait le double.
        """
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        link(session, user, home, far,
             flows=[{'resource': 'iron', 'rate': 10.0, 'to_origin': False}])

        home.iron = 5000
        far.iron = 0
        session.commit()

        far._run_trade(hours=5.0)
        assert far.iron == 0


# ── Les routes ───────────────────────────────────────────────────────────────

class TestTheTradeRoutes:

    def freighter(self, session, territory, user, count=1):
        fleet = Fleet.create(system_id=territory.system_id, user=user,
                             name="convoi", orbiting_territory_id=territory.id)
        fleet.add_ships(ship_type=ShipType.Freighter, amount=count)
        session.commit()
        return fleet

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_opening_needs_a_freighter_at_the_destination(
            self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)

        answer = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id})
        assert answer.status_code == 400
        assert "Freighter" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_with_the_freighter_it_opens_and_consumes_it(
            self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        fleet = self.freighter(session, far, user, count=2)

        answer = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id})
        assert answer.status_code == 200

        carried = next(s for s in fleet.ships if s.type == ShipType.Freighter)
        assert carried.count == 1
        assert Territory.get(id=far.id).is_connected is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_world_that_is_not_yours_is_not_found(
            self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        stranger = outpost(session, base_universe, user, position="5_5_5")
        stranger.user_id = None
        session.commit()

        answer = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": stranger.id})
        assert answer.status_code == 404

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_two_worlds_are_linked_once(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user, count=2)

        assert client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).status_code == 200
        # Meme dans l'autre sens : une route n'a pas de sens.
        answer = client.post('/api/trade', json={
            "origin_id": far.id, "destination_id": home.id})
        assert answer.status_code == 409

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_flows_are_declared_and_read_back(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user)

        opened = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).json

        answer = client.post('/api/trade/%d' % opened['id'], json={
            "flows": [{"resource": "food", "rate": 42, "to_origin": False}]})
        assert answer.status_code == 200
        assert answer.json['flows'] == [
            {"resource": "food", "rate": 42.0, "to_origin": False}]

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_energy_does_not_travel(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user)

        opened = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).json

        answer = client.post('/api/trade/%d' % opened['id'], json={
            "flows": [{"resource": "energy", "rate": 10}]})
        assert answer.status_code == 400
        assert "energy" in answer.json['message'].lower()

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_population_does_not_travel(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user)

        opened = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).json

        answer = client.post('/api/trade/%d' % opened['id'], json={
            "flows": [{"resource": "population", "rate": 10}]})
        assert answer.status_code == 400

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_line_can_be_dismantled(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user)

        opened = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).json

        assert client.delete('/api/trade/%d' % opened['id']).status_code == 200
        assert client.delete('/api/trade/%d' % opened['id']).status_code == 409

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_list_keeps_closed_lines(self, client, session, base_universe):
        user = me(base_universe)
        home = capital(session, base_universe)
        far = outpost(session, base_universe, user)
        self.freighter(session, far, user)

        opened = client.post('/api/trade', json={
            "origin_id": home.id, "destination_id": far.id}).json
        client.delete('/api/trade/%d' % opened['id'])

        listed = client.get('/api/trade').json['lines']
        assert len(listed) == 1
        assert listed[0]['open'] is False


# ── L'amorcage ───────────────────────────────────────────────────────────────

class TestANewColonyIsNeverBornIsolated:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_founding_opens_a_line_to_the_capital(
            self, client, session, base_universe):
        """
        Sans cela, une colonie perdrait de la stabilite des la premiere heure —
        sans depot, et sans les ressources pour en batir un.
        """
        user = me(base_universe)
        capital(session, base_universe)

        system = System.create(galaxy=base_universe['galaxy'], position="4_4_4")
        session.commit()
        target = system.territories[0]
        target.archetype = PlanetArchetype.telluric
        target.deposits = target.archetype.roll_deposits()
        session.commit()

        fleet = Fleet.create(system_id=target.system_id, user=user,
                             name="colons", orbiting_territory_id=target.id)
        fleet.add_ships(ship_type=ShipType.ColonyShip, amount=1)
        session.commit()

        assert client.post('/api/territory/%d' % target.id).status_code == 200

        founded = Territory.get(id=target.id)
        assert founded.is_connected is True
        assert TradeLine.between(
            origin=founded, destination=user.territories[0]) is not None
