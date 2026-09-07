# -*- coding: utf-8 -*-

"""
Le graphe des liaisons entre etoiles, pris a la source.

`tests/api/game/travel.py` verifie deja qu'une flotte suit ces liaisons, mais a
travers une galaxie en base et des requetes HTTP : ce qu'il montre, c'est un
trajet, pas la regle qui l'a dessine. Ici les etoiles sont posees a la main et
on lit le graphe qui en sort.

Trois choses ne sont atteignables qu'a ce niveau :

  · l'elargissement du rayon pour une etoile trop isolee, qui demande une
    galaxie ou presque personne ne se voit ;
  · la borne qui arrete cet elargissement -- une galaxie d'une seule etoile,
    qui bouclerait indefiniment sans elle ;
  · le cache, dont tout l'interet est de ne pas recalculer : on ne peut le
    verifier qu'en comptant les calculs.

La regle est jumelle de celle du client Unity (`StarNeighbourhood`) : le serveur
la reproduit sans pouvoir la confronter a l'original. Ces tests disent ce que le
serveur applique ; que les deux s'accordent, seule la lecture des deux codes le
dit.
"""

import pytest

from app.models.game import starlanes
from app.models.game.starlanes import (
    LINK_SEARCH_RADIUS, LINKS_PER_STAR, MIN_LINKS_PER_STAR)


#: Un amas ou chaque etoile a de quoi se satisfaire sans elargir sa recherche,
#: et dont les deux bouts sont hors de portee l'un de l'autre.
#:
#:   A ---4--- B ---4--- C      Les deux etoiles basses, a trois unites au-dessus,
#:   |                   |      donnent a A et a C leur seconde voisine. Sans
#:   A2                  C2     elles, chacune elargirait jusqu'a rejoindre
#:                              l'autre, et il n'y aurait plus de detour a faire.
CHAIN = ["0_0_0", "0_3_0", "4_0_0", "8_0_0", "8_3_0"]
A, A2, B, C, C2 = range(1, 6)


def degrees(galaxy_name, systems):
    return {s.id: set(starlanes.neighbours(galaxy_name, s.id)) for s in systems}


class TestCoordinates:

    def test_a_position_reads_as_three_coordinates(self, stub):
        assert starlanes._coordinates(stub(position="3_4_12")) == (3.0, 4.0, 12.0)

    @pytest.mark.parametrize("position", [None, "", "1_2", "here_there_yonder"])
    def test_an_unreadable_position_lands_at_the_origin(self, stub, position):
        """
        Une position illisible place l'etoile a l'origine, sans lever.
        ---
        La colonne est du texte libre, ecrite par le generateur : une seule
        valeur abimee ne doit pas emporter le graphe de la galaxie entiere,
        c'est-a-dire la carte, les routes, et tout deplacement de flotte.
        """
        assert starlanes._coordinates(stub(position=position)) == (0.0, 0.0, 0.0)


class TestNeighbourhood:

    def test_stars_beyond_the_radius_are_not_linked(self, place):
        """Six unites, et pas une de plus tant qu'on a deux voisines."""
        systems = place(CHAIN)
        around = degrees("chain", systems)

        assert around[A] == {A2, B}
        assert around[C] == {C2, B}
        # Huit unites separent les deux bouts de la chaine : au-dela du rayon.
        assert C not in around[A]

    def test_a_link_holds_both_ways(self, place):
        """
        Les liaisons sont reciproques, comme les traits que dessine le client.
        ---
        Une liaison a sens unique ferait une flotte capable d'aller quelque part
        sans pouvoir en revenir, la ou le joueur ne voit qu'un seul trait.
        """
        systems = place(CHAIN)
        around = degrees("chain", systems)

        for origin, others in around.items():
            for other in others:
                assert origin in around[other]

    def test_a_star_keeps_the_distance_to_each_neighbour(self, place):
        place(CHAIN)
        around = starlanes.neighbours("chain", A)

        assert around[A2] == pytest.approx(3.0)
        assert around[B] == pytest.approx(4.0)

    def test_an_isolated_star_widens_its_search(self, place):
        """
        Une etoile trop seule elargit son rayon jusqu'a deux voisines.
        ---
        Sans cela une galaxie clairsemee compterait des etoiles sans aucune
        liaison, donc des mondes ou une flotte ne pourrait ni se rendre ni etre
        secourue. C'est le seul cas ou le rayon de six unites est depasse.
        """
        systems = place(["0_0_0", "50_0_0", "100_0_0"])
        around = degrees("sparse", systems)

        assert all(len(others) >= MIN_LINKS_PER_STAR for others in around.values())
        # Bien au-dela du rayon nominal : c'est tout le propos.
        assert starlanes.neighbours("sparse", 1)[3] == pytest.approx(100.0)
        assert 100.0 > LINK_SEARCH_RADIUS

    def test_a_lone_star_does_not_search_forever(self, place):
        """
        Une galaxie d'une seule etoile s'arrete, et ne relie rien.
        ---
        L'elargissement cherche deux voisines ; quand il n'y en a aucune a
        trouver, seule la borne de la diagonale l'arrete. Ce test est la pour
        elle : sans elle, le calcul ne rendrait jamais la main.
        """
        place(["0_0_0"])

        assert starlanes.neighbours("alone", 1) == {}
        assert starlanes.edges("alone") == []

    def test_a_star_chooses_at_most_five_neighbours(self, place):
        """
        Cinq voisines au plus par etoile -- celles qu'elle choisit.
        ---
        Elle peut en compter davantage au bout du compte : la reciprocite lui
        amene celles qui l'ont choisie. Ce qui est borne, c'est le choix, et
        c'est lui qui empeche un amas dense de devenir un graphe complet ou
        toutes les routes se valent.
        """
        # Neuf etoiles alignees a une unite d'intervalle : toutes se voient.
        systems = place(["{}_0_0".format(x) for x in range(9)])
        points = {s.id: starlanes._coordinates(s) for s in systems}
        graph = starlanes.lanes_of("dense")

        for system in systems:
            nearest = sorted(
                (starlanes._distance(points[system.id], points[other.id]), other.id)
                for other in systems if other.id != system.id)[:LINKS_PER_STAR]
            assert {other for _, other in nearest} <= set(graph[system.id])

        # Le graphe reste creux : la moitie des paires possibles au plus.
        possible = len(systems) * (len(systems) - 1) / 2
        assert len(starlanes.edges("dense")) < possible


class TestRoute:

    def test_a_route_runs_from_origin_to_destination_by_lanes(self, place):
        """
        Un chemin est une suite de liaisons, bornes comprises.
        ---
        Le contrat de `route` : la flotte part de chez elle, arrive ou on l'a
        envoyee, et chaque saut du chemin est une liaison qui existe.
        """
        place(CHAIN)
        path = starlanes.route("chain", A, C)

        assert path[0] == A and path[-1] == C
        assert path == [A, B, C]
        for start, end in zip(path, path[1:]):
            assert end in starlanes.neighbours("chain", start)

    def test_going_nowhere_is_a_route_of_one(self, place):
        place(CHAIN)
        assert starlanes.route("chain", B, B) == [B]

    def test_an_unknown_star_has_no_route(self, place):
        place(CHAIN)
        assert starlanes.route("chain", A, 999) is None
        assert starlanes.route("chain", 999, A) is None

    def test_two_clusters_that_suffice_to_themselves_never_meet(self, place):
        """
        Deux amas assez serres pour se satisfaire restent injoignables.
        ---
        C'est la seule facon d'etre hors d'atteinte : une etoile isolee, elle,
        finit toujours par trouver deux voisines. Le jeu peut donc avoir des
        regions coupees, et le modele doit savoir le dire plutot que rendre un
        chemin fantaisiste.
        """
        place(CHAIN + ["100_0_0", "104_0_0", "102_3_0"])

        assert starlanes.route("split", A, 6) is None
        assert starlanes.route("split", 6, A) is None


class TestEdgesAndLegs:

    def test_each_lane_is_published_once(self, place):
        """
        Le graphe interne est reciproque, la liste des liaisons ne l'est pas.
        ---
        Une liaison rendue deux fois, c'est un trait dessine deux fois par le
        client : invisible a l'oeil, double sur le reseau et au rendu.
        """
        systems = place(CHAIN)
        pairs = [(origin, other) for origin, other, _ in starlanes.edges("chain")]

        assert len(pairs) == len(set(pairs))
        assert all(origin < other for origin, other in pairs)
        assert pairs == sorted(pairs)

        around = degrees("chain", systems)
        assert len(pairs) == sum(len(others) for others in around.values()) / 2

    def test_a_lane_length_is_the_distance_between_its_stars(self, place):
        place(CHAIN)
        lengths = {(origin, other): length
                   for origin, other, length in starlanes.edges("chain")}

        assert lengths[(A, B)] == pytest.approx(4.0)
        assert lengths[(A, A2)] == pytest.approx(3.0)

    def test_legs_measure_each_hop_of_a_route(self, place):
        """
        La longueur de chaque saut, calculee a part de la route.
        ---
        Un ordre donne en cours de vol reprend un chemin deja etabli et n'a
        besoin que de ses longueurs : les deux calculs sont donc separes.
        """
        place(CHAIN)
        path = starlanes.route("chain", A, C)

        assert starlanes.leg_lengths("chain", path) == pytest.approx([4.0, 4.0])
        assert starlanes.leg_lengths("chain", [A]) == []

    def test_a_hop_that_is_not_a_lane_measures_zero(self, place):
        """
        Un saut inexistant vaut zero seconde, il ne leve pas.
        ---
        Les chemins sont figes au depart et relus plus tard : entre-temps la
        galaxie peut s'etre agrandie. Mieux vaut un saut devenu instantane
        qu'une erreur serveur a la lecture d'une flotte.
        """
        place(CHAIN)
        assert starlanes.leg_lengths("chain", [A, C]) == [0.0]


class TestCache:

    @pytest.fixture(name="count_builds")
    def count_builds(self, monkeypatch):
        calls = []
        original = starlanes._build

        def counted(systems):
            calls.append(len(systems))
            return original(systems)

        monkeypatch.setattr(starlanes, '_build', counted)
        return calls

    def test_a_galaxy_is_computed_once(self, place, count_builds):
        """
        Le graphe se calcule au premier appel et se relit ensuite.
        ---
        Il coute un carre du nombre d'etoiles, et il est demande a chaque
        lecture de flotte : sans cache, la carte se paierait a chaque coup
        d'oeil.
        """
        place(CHAIN)

        starlanes.lanes_of("chain")
        starlanes.route("chain", A, C)
        starlanes.edges("chain")

        assert len(count_builds) == 1

    def test_moving_a_star_recomputes_the_graph(self, place, count_builds):
        """
        Le cache se controle lui-meme, en comparant ce qui l'a produit.
        ---
        Positions et identifiants sont releves a chaque appel : un systeme
        ajoute, deplace ou supprime refait le graphe sans que personne n'ait a
        penser a l'invalider. C'est la seule garantie qu'une galaxie qui
        s'agrandit en cours de partie reste navigable.
        """
        systems = place(CHAIN)
        starlanes.lanes_of("chain")

        systems[-1].position = "40_0_0"
        starlanes.lanes_of("chain")

        assert len(count_builds) == 2

    def test_forgetting_one_galaxy_leaves_the_others(self, place, count_builds):
        place(CHAIN)
        starlanes.lanes_of("chain")

        starlanes.forget("elsewhere")
        starlanes.lanes_of("chain")
        assert len(count_builds) == 1

        starlanes.forget("chain")
        starlanes.lanes_of("chain")
        assert len(count_builds) == 2
