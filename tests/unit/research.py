# -*- coding: utf-8 -*-

"""
L'arbre technologique, et le moteur de modificateurs qui le rend applicable.

Les trois sujets de ce fichier ne se rencontrent nulle part ailleurs :

  · la composition des modificateurs, trois lignes de calcul sans etat et sans
    base, dont depend pourtant tout ce qu'un joueur gagne a chercher ;
  · la table des noeuds — ses couts, ses courbes, ses prerequis. Une table se
    relit mal a l'oeil : ce qu'on eprouve ici, ce sont ses invariants ;
  · la progression d'un joueur dans cette table : ce qui s'ouvre, ce qui reste
    ferme, et ce que la fiche annonce.

Aucun de ces tests n'a besoin d'une base. C'est voulu, et c'est ce qui permet
de les lancer a chaque frappe : les regles du jeu se calculent, elles ne se
requetent pas. Les lectures qui iraient chercher en base — recherches en
cours, encaissement des niveaux finis — rendent vide sur un joueur monte a la
main, et les tests d'API les couvrent.

Les technologies appartiennent au joueur et non a une galaxie : c'est pourquoi
aucun reglage de partie ne les touche, et pourquoi rien de ce fichier n'a
besoin de `GalaxySettings`.
"""

from datetime import datetime, timedelta

import pytest

from app.models.game.community.faction import (
    Faction, FactionAdvantages, FactionAdvantageScope, FactionAdvantageType)
from app.models.game.modifiers import (
    MATERIALS, Modifier, ModifierScope, ModifierSet, ModifierType)
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import (
    Branch, LEGACY_NAMES, NodeKind, TIER_REQUIREMENTS, TechnologyType, tree)
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


def a_researcher(faction=None, levels=None, choices=None):
    """
    Un joueur et son arbre, entierement en memoire.
    ---
    Les 36 lignes sont posees comme `Technology.initialize` les pose, puis les
    niveaux demandes sont appliques. Le joueur n'etant rattache a aucune
    session, `Technology.all` lit cette liste-la : voir la docstring de la
    methode.
    """
    user = User(username="chercheuse", email="c@testing.com")
    user.id = 1
    user.faction = faction
    levels = levels or {}
    choices = choices or {}

    for node in TechnologyType:
        user.technologies.append(Technology(
            type=node,
            user_id=1,
            level=levels.get(node.name, 0),
            choice=choices.get(node.name),
            created_at=MOMENT,
            updated_at=MOMENT,
        ))
    return user


def technology_of(user, node):
    return next(t for t in user.technologies if t.type is node)


class TestModifierComposition:
    """
    Le calcul par lequel passe tout ce qui modifie une valeur du jeu.
    """

    def test_a_modifier_lifts_what_it_covers(self):
        modifiers = ModifierSet([
            Modifier(ModifierType.Production, ModifierScope.Resource, percentage=10)])

        assert modifiers.apply(100, scope=ModifierScope.Resource) == pytest.approx(110)

    def test_a_modifier_of_another_scope_does_not_apply(self):
        modifiers = ModifierSet([
            Modifier(ModifierType.Power, ModifierScope.Ships, percentage=10)])

        assert modifiers.apply(100, scope=ModifierScope.Resource) == 100

    def test_a_named_target_applies_to_that_one_alone(self):
        modifiers = ModifierSet([Modifier(
            ModifierType.Production, ModifierScope.Resource,
            percentage=50, target=ResourceType.silicium.name)])

        assert modifiers.apply(
            100, scope=ModifierScope.Resource,
            target=ResourceType.silicium.name) == pytest.approx(150)
        assert modifiers.apply(
            100, scope=ModifierScope.Resource,
            target=ResourceType.titanium.name) == 100

    def test_a_targeted_modifier_stays_out_of_an_untargeted_question(self):
        """
        Sans cette regle, le bonus silicium des Technocrates s'appliquerait a
        toute demande qui ne nomme pas de ressource — c'est-a-dire a tout.
        """
        modifiers = ModifierSet([Modifier(
            ModifierType.Production, ModifierScope.Resource,
            percentage=50, target=ResourceType.silicium.name)])

        assert modifiers.apply(100, scope=ModifierScope.Resource) == 100

    def test_a_collective_target_covers_every_material(self):
        modifiers = ModifierSet([Modifier(
            ModifierType.Production, ModifierScope.Resource,
            percentage=10, target=MATERIALS)])

        assert modifiers.apply(
            100, scope=ModifierScope.Resource, target='iron') == pytest.approx(110)
        assert modifiers.apply(
            100, scope=ModifierScope.Resource, target='credits') == 100

    def test_percentages_of_the_same_scope_add_up_and_do_not_compound(self):
        """
        Deux fois +10 % font +20 %, pas +21 %.
        ---
        C'est ce que la fiche d'un noeud annonce au joueur. Une composition
        ferait diverger l'affichage du calcul des le troisieme bonus.
        """
        modifiers = ModifierSet([
            Modifier(ModifierType.Production, ModifierScope.Resource, percentage=10),
            Modifier(ModifierType.Production, ModifierScope.Resource, percentage=10),
        ])

        assert modifiers.apply(100, scope=ModifierScope.Resource) == pytest.approx(120)

    def test_a_flat_term_lands_after_the_percentage(self):
        modifiers = ModifierSet([
            Modifier(ModifierType.Capacity, ModifierScope.Research, percentage=100),
            Modifier(ModifierType.Capacity, ModifierScope.Research, flat=2),
        ])

        assert modifiers.apply(3, scope=ModifierScope.Research) == 8

    def test_a_pile_of_reductions_never_reaches_zero(self):
        """
        Un multiplicateur nul rendrait une recherche instantanee et un vaisseau
        gratuit. Le plancher est la pour que ni l'un ni l'autre n'arrive.
        """
        modifiers = ModifierSet([
            Modifier(ModifierType.Cost, ModifierScope.Ships, percentage=-500)])

        assert modifiers.apply(100, scope=ModifierScope.Ships) == pytest.approx(5)

    def test_a_time_modifier_signs_like_every_other(self):
        """
        Une seule regle de signe pour toute la table : le pourcentage dit ce
        qu'il fait A LA VALEUR. `-20` sur une duree la raccourcit, comme `-20`
        sur un cout le baisse.
        ---
        Deux conventions opposees se cotoyaient : la faction des Technocrates
        porte `-10` pour « dix pour cent plus vite », et `TimeReduce` avait ete
        lu ici comme « un positif raccourcit ». Monter `Architecture de calcul`
        accelerait alors les recherches pendant que la faction les ralentissait.
        """
        modifiers = ModifierSet([Modifier(
            ModifierType.TimeReduce, ModifierScope.Technologies, percentage=-20)])

        assert modifiers.shorten(100, scope=ModifierScope.Technologies) == pytest.approx(80)

    def test_a_positive_time_modifier_lengthens(self):
        """
        « Production de masse » allonge l'assemblage : les deux signes se
        rencontrent bel et bien dans la table.
        """
        modifiers = ModifierSet([Modifier(
            ModifierType.TimeReduce, ModifierScope.Ships, percentage=10)])

        assert modifiers.shorten(100, scope=ModifierScope.Ships) == pytest.approx(110)

    def test_an_unlock_is_a_presence_and_not_a_value(self):
        modifiers = ModifierSet([Modifier(
            ModifierType.Unlock, ModifierScope.Defenses, target='LaserArtillery')])

        assert modifiers.unlocked(ModifierScope.Defenses, 'LaserArtillery')
        assert not modifiers.unlocked(ModifierScope.Defenses, 'IonArtillery')

    def test_an_empty_set_changes_nothing(self):
        assert ModifierSet().apply(100, scope=ModifierScope.Resource) == 100


class TestFactionAdvantages:
    """
    Une faction n'a plus de moteur a elle : elle rend des modificateurs. Ces
    tests verifient que le raccourci historique donne toujours les memes
    reponses.
    """

    def test_an_advantage_lifts_what_it_covers(self):
        faction = a_faction((
            FactionAdvantageType.Production,
            FactionAdvantageScope.Resource,
            {'percentage': 10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == pytest.approx(110)

    def test_an_advantage_of_another_category_does_not_apply(self):
        faction = a_faction((
            FactionAdvantageType.Power,
            FactionAdvantageScope.Ships,
            {'percentage': 10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == 100

    def test_a_named_scope_applies_to_that_one_alone(self):
        faction = a_faction((
            FactionAdvantageType.Production,
            FactionAdvantageScope.Resource,
            {'percentage': 50, 'scope': ResourceType.silicium.name},
        ))

        assert faction.apply(
            obj=100,
            advantage_scope=FactionAdvantageScope.Resource,
            scope=ResourceType.silicium.name) == pytest.approx(150)
        assert faction.apply(
            obj=100,
            advantage_scope=FactionAdvantageScope.Resource,
            scope=ResourceType.titanium.name) == 100

    def test_a_negative_percentage_takes_away(self):
        faction = a_faction((
            FactionAdvantageType.TimeReduce,
            FactionAdvantageScope.Technologies,
            {'percentage': -10},
        ))

        assert faction.apply(
            obj=100, advantage_scope=FactionAdvantageScope.Technologies) == pytest.approx(90)

    def test_a_faction_without_advantages_changes_nothing(self):
        assert a_faction().apply(
            obj=100, advantage_scope=FactionAdvantageScope.Resource) == 100

    def test_a_faction_says_who_it_is(self):
        faction = a_faction()
        faction.id = 3

        assert faction.serialize == {'id': 3, 'name': "Cobayes"}


class TestTechnologyCatalogue:
    """
    Les invariants de la table. Une table de 36 entrees se relit mal a l'oeil :
    ce sont ces regles-la qui attrapent une faute de frappe.
    """

    def test_every_cost_names_a_resource_the_game_knows(self):
        known = {resource.name for resource in ResourceType}

        for node in TechnologyType:
            assert set(node.base_cost) <= known, node.name

    def test_every_node_is_paid_in_data(self):
        """
        Les Donnees sont la monnaie de la recherche : un noeud qui n'en
        demanderait pas se paierait uniquement en materiaux, et l'academie
        cesserait de servir a quoi que ce soit.
        """
        for node in TechnologyType:
            assert node.base_cost.get('research'), node.name

    def test_every_requirement_names_a_node_that_exists(self):
        names = {node.name for node in TechnologyType}

        for node in TechnologyType:
            assert set(node.requires) <= names, node.name

    def test_a_requirement_never_asks_more_than_its_target_can_give(self):
        """
        Un prerequis de niveau 12 sur un noeud plafonne a 10 fermerait sa suite
        pour toujours, sans que rien ne le signale.
        """
        for node in TechnologyType:
            for name, level in node.requires.items():
                required = TechnologyType.get_by_name(name)
                if required.is_endless:
                    continue
                assert level <= required.max_level, (node.name, name)

    def test_a_requirement_never_points_at_a_later_tier(self):
        """
        Un noeud ne peut pas dependre de quelque chose qui s'ouvre apres lui :
        la voie serait sans issue.
        """
        for node in TechnologyType:
            for name in node.requires:
                assert TechnologyType.get_by_name(name).tier <= node.tier, node.name

    def test_the_first_tier_of_every_branch_is_reachable_from_nothing(self):
        """
        Chaque branche doit avoir une porte d'entree gratuite, sans quoi elle
        serait inaccessible : ses paliers s'ouvrent avec les niveaux depenses
        dedans, et on ne peut en depenser aucun.
        """
        for branch in Branch:
            openings = [
                node for node in TechnologyType.of_branch(branch)
                if node.tier == 1 and not node.requires
            ]
            assert openings, branch.name

    def test_the_first_level_costs_exactly_the_base_price(self):
        for node in TechnologyType:
            assert node.price(level=1) == node.base_cost

    def test_each_level_costs_more_than_the_previous(self):
        for node in TechnologyType:
            for level in range(1, 5):
                cheaper = node.price(level)
                dearer = node.price(level + 1)
                for resource, amount in cheaper.items():
                    assert dearer[resource] == pytest.approx(amount * node.cost_factor), (
                        node.name, resource)

    def test_a_price_asks_for_data_and_nothing_else(self):
        """
        Chercher se paie en Donnees et en attente.

        L'arbre facturait aussi des materiaux et des credits, chaque branche
        ayant son materiau signature. C'en faisait un second chantier : on
        montait un noeud parce qu'on avait du titane, pas parce qu'on voulait ce
        qu'il ouvre — et un joueur riche en minerai avancait plus vite qu'un
        joueur qui avait bati des academies.
        """
        for node in TechnologyType:
            assert set(node.price(level=1)) == {'research'}, node.name

    def test_the_price_is_never_zero(self):
        """
        Une seule ressource au prix : si elle tombait a zero quelque part, le
        noeud deviendrait gratuit sans que rien ne le signale.
        """
        for node in TechnologyType:
            assert node.price(level=1)['research'] > 0, node.name

    def test_research_takes_longer_at_each_level(self):
        for node in TechnologyType:
            for level in range(0, 5):
                assert node.duration(level + 1) > node.duration(level), node.name

    def test_the_curve_stays_playable_where_the_old_one_did_not(self):
        """
        `5 x 3^x` posait le niveau 10 a trois jours et demi et le niveau 15 a
        deux ans : aucun noeud profond n'etait jouable, donc aucun arbre ne
        tenait dans le temps. Le seuil retenu — le DERNIER niveau d'un rang sous
        les deux semaines — est ce qui rend un rang de vingt niveaux atteignable
        au lieu d'ornemental.
        """
        ranks = [n for n in TechnologyType if n.kind == NodeKind.rank]
        assert ranks

        for node in ranks:
            assert node.duration(node.max_level) < 14 * 24 * 3600, node.name

    def test_a_node_is_found_by_its_name(self):
        assert TechnologyType.get_by_name('laser') is TechnologyType.laser
        assert TechnologyType.get_by_name('telepathie') is None

    def test_every_legacy_name_lands_on_a_node_that_exists(self):
        """
        Les sept technologies d'avant sont renommees par la migration : un joueur
        qui avait monte `computer` retrouve son niveau sur `calcul`.
        """
        names = {node.name for node in TechnologyType}

        for old, new in LEGACY_NAMES.items():
            assert new in names, old

    def test_only_the_endless_nodes_have_no_last_level(self):
        for node in TechnologyType:
            assert node.is_endless == (node.kind == NodeKind.endless), node.name

    def test_a_doctrine_offers_a_real_choice(self):
        doctrines = [n for n in TechnologyType if n.kind == NodeKind.doctrine]
        assert doctrines

        for node in doctrines:
            assert len(node.options) >= 2, node.name
            keys = [option['key'] for option in node.options]
            assert len(set(keys)) == len(keys), node.name
            for option in node.options:
                assert option['effects'], (node.name, option['key'])

    def test_only_a_doctrine_offers_one(self):
        for node in TechnologyType:
            if node.kind != NodeKind.doctrine:
                assert not node.options, node.name

    def test_every_effect_carries_the_sentence_the_client_shows(self):
        for node in TechnologyType:
            effects = list(node.effects)
            for option in node.options:
                effects += option['effects']
            for spec in effects:
                assert spec['label'], node.name

    def test_a_rank_gains_something_at_every_level(self):
        for node in TechnologyType:
            if node.kind not in (NodeKind.rank, NodeKind.endless):
                continue
            assert any(
                spec['per_level'] or spec['flat_per_level'] for spec in node.effects), \
                node.name

    def test_every_tier_is_declared(self):
        for node in TechnologyType:
            assert node.tier in TIER_REQUIREMENTS, node.name

    def test_every_branch_covers_every_tier(self):
        """
        Un palier vide dans une branche est un trou qu'on ne peut pas traverser :
        les niveaux s'y depensent pour rien, et le palier suivant reste ferme.
        """
        for branch in Branch:
            tiers = {node.tier for node in TechnologyType.of_branch(branch)}
            assert tiers == set(TIER_REQUIREMENTS), branch.name

    def test_every_branch_can_reach_its_last_tier(self):
        """
        Le seuil du dernier palier doit rester sous ce que la branche peut
        rendre. Sinon il faudrait tout monter pour l'ouvrir — et un palier qui
        exige d'avoir fini n'est pas un palier, c'est une recompense.
        """
        deepest = TIER_REQUIREMENTS[max(TIER_REQUIREMENTS)]
        for branch in Branch:
            available = sum(
                node.max_level for node in TechnologyType.of_branch(branch)
                if not node.is_endless)
            assert available > deepest, branch.name

    def test_the_prerequisites_have_no_cycle(self):
        """
        Deux noeuds qui s'exigent l'un l'autre sont inatteignables a jamais, et
        rien dans l'interface ne le dirait : ils s'afficheraient simplement
        verrouilles pour toujours.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {node.name: WHITE for node in TechnologyType}

        def visit(name, path):
            assert colour[name] != GREY, " -> ".join(path + [name])
            if colour[name] == BLACK:
                return
            colour[name] = GREY
            for required in TechnologyType.get_by_name(name).requires:
                visit(required, path + [name])
            colour[name] = BLACK

        for node in TechnologyType:
            visit(node.name, [])

    def test_the_tree_actually_branches(self):
        """
        Un arbre dont chaque noeud n'a qu'une suite n'est pas un arbre : c'est
        une file. On exige donc des fourches — des noeuds qui menent a plusieurs
        endroits — dans chaque branche.
        """
        successors = {node.name: 0 for node in TechnologyType}
        for node in TechnologyType:
            for required in node.requires:
                successors[required] += 1

        for branch in Branch:
            forks = [n for n in TechnologyType.of_branch(branch)
                     if successors[n.name] >= 2]
            assert len(forks) >= 5, (branch.name, len(forks))

    def test_the_tree_also_converges(self):
        """
        Le pendant de la fourche : des noeuds qui reclament DEUX voies. Sans
        eux, on descendrait une voie de bout en bout sans jamais regarder les
        autres.
        """
        for branch in Branch:
            joins = [n for n in TechnologyType.of_branch(branch)
                     if len(n.requires) >= 2]
            assert len(joins) >= 5, (branch.name, len(joins))

    def test_no_node_is_a_dead_end_before_the_last_tier(self):
        """
        Une voie sans issue au milieu de l'arbre est un piege : on y depense des
        niveaux qui n'ouvrent rien. Les feuilles n'ont leur place qu'au fond.
        """
        successors = {node.name: 0 for node in TechnologyType}
        for node in TechnologyType:
            for required in node.requires:
                successors[required] += 1

        for node in TechnologyType:
            if node.tier >= 9 or node.unlocks:
                continue
            assert successors[node.name] > 0, node.name

    def test_every_branch_offers_its_own_definitive_choice(self):
        """
        Une doctrine par branche : c'est la fourche qu'on ne peut pas reprendre,
        et une branche qui n'en a pas se descend sans jamais rien decider.
        """
        for branch in Branch:
            doctrines = [n for n in TechnologyType.of_branch(branch)
                         if n.kind == NodeKind.doctrine]
            assert len(doctrines) == 1, (branch.name, len(doctrines))

    def test_the_branches_depend_on_one_another(self):
        """
        Des prerequis qui traversent les branches : sans eux, cinq arbres
        independants plutot qu'un seul.
        """
        crossings = [
            (node.name, required)
            for node in TechnologyType
            for required in node.requires
            if TechnologyType.get_by_name(required).branch != node.branch
        ]
        assert len(crossings) >= 15, len(crossings)
        touched = {TechnologyType.get_by_name(n).branch for n, _ in crossings}
        assert touched == set(Branch), touched

    def test_the_tiers_climb(self):
        thresholds = [TIER_REQUIREMENTS[t] for t in sorted(TIER_REQUIREMENTS)]
        assert thresholds == sorted(thresholds)
        assert thresholds[0] == 0, "le premier palier ne se merite pas"

    def test_a_breakthrough_costs_more_than_a_rank_of_its_tier(self):
        """
        Une percee n'a qu'un niveau : tout son prix est dans sa base. Au meme
        tarif qu'un rang, elle serait le noeud le moins cher de son palier tout
        en etant le plus decisif.
        """
        for tier in TIER_REQUIREMENTS:
            ranks = [n for n in TechnologyType
                     if n.tier == tier and n.kind == NodeKind.rank]
            breaks = [n for n in TechnologyType
                      if n.tier == tier and n.kind == NodeKind.breakthrough]
            if not ranks or not breaks:
                continue
            cheapest = min(b.base_cost['research'] for b in breaks)
            dearest = max(r.base_cost['research'] for r in ranks)
            assert cheapest > dearest, tier

    def test_a_deeper_tier_costs_more(self):
        """
        La courbe monte d'un palier a l'autre — a nature egale.
        ---
        La comparaison se fait par nature de noeud et non tous noeuds confondus :
        une percee vaut huit niveaux du rang voisin, si bien que le palier IX,
        qui n'a que des percees, coute plus cher que le premier niveau du noeud
        infini du palier X. Ce n'est pas une anomalie — un noeud infini commence
        petit et n'a pas de fin — mais cela rend la comparaison brute muette.
        """
        for kind in (NodeKind.rank, NodeKind.breakthrough):
            by_tier = {}
            for node in TechnologyType:
                if node.kind != kind:
                    continue
                by_tier.setdefault(node.tier, []).append(node.base_cost['research'])
            cheapest = [min(by_tier[t]) for t in sorted(by_tier)]
            assert cheapest == sorted(cheapest), kind


class TestUnlocks:
    """
    Ce qu'un noeud ouvre est lu dans les tables d'unites, jamais recopie dans
    l'arbre : deux declarations de la meme regle finissent par diverger.
    """

    def test_the_laser_line_opens_the_artillery_that_asked_for_it(self):
        """
        `DefenseType.LaserArtillery` reclamait `laser: 5` sur une technologie
        qui n'existait pas. Elle existe — et le deblocage tombe au niveau 1.
        """
        assert TechnologyType.laser.unlocks['defenses']['LaserArtillery'] == 1

    def test_everything_opens_at_the_first_level(self):
        """
        L'invariant de l'arbre : ce qu'un noeud ouvre, il l'ouvre des qu'on l'a.

        Les niveaux declares valaient jusqu'a huit. Une coque tenue derriere
        `artillerie_lourde 6` restait invisible pendant cinq niveaux — le joueur
        payait sans rien voir arriver, et la fiche du noeud annoncait un
        deblocage qu'elle ne tenait pas avant des heures. Les niveaux suivants
        n'ajoutent que de la puissance.

        Teste sur les tables d'unites, qui sont la source : l'arbre ne fait que
        les retourner.
        """
        from app.models.game.buildings import BuildingType
        from app.models.game.defense import DefenseType
        from app.models.game.ship import ShipType

        for catalogue in (BuildingType, ShipType, DefenseType):
            for unit in catalogue:
                required = (unit.value.get('requirements') or {}).get('technologies') or {}
                for name, level in required.items():
                    assert level == 1, (unit.name, name, level)

    def test_a_node_that_opens_nothing_says_so(self):
        assert TechnologyType.extraction.unlocks == {}

    def test_an_unlock_appears_with_the_first_level(self):
        """
        Rien au niveau 0 — un noeud non acquis n'ouvre rien — et tout au
        niveau 1.
        """
        none = TechnologyType.laser.modifiers_at(level=0)
        first = TechnologyType.laser.modifiers_at(level=1)

        assert not any(m.type == ModifierType.Unlock for m in none)
        assert any(
            m.type == ModifierType.Unlock and m.target == 'LaserArtillery'
            for m in first)

    def test_the_unlocks_are_spread_across_the_tree(self):
        """
        Un arbre dont tous les deblocages tombent au meme endroit n'a qu'un
        moment interessant. On verifie qu'ils s'etalent, et qu'aucune branche
        n'en monopolise la totalite.
        """
        tiers = {node.tier for node in TechnologyType if node.unlocks}
        assert len(tiers) >= 5, tiers

        branches = {node.branch for node in TechnologyType if node.unlocks}
        assert len(branches) >= 3, branches

    def test_the_starter_pieces_stay_free(self):
        """
        Un monde neuf doit pouvoir se defendre et assembler avant d'avoir
        cherche quoi que ce soit : sans cela, la premiere heure de jeu n'a pas
        d'issue. Meme raison pour la ferme, la centrale et l'academie —
        verrouiller la recherche derriere la recherche n'aurait pas de fin.
        """
        from app.models.game.buildings import BuildingType
        from app.models.game.defense import DefenseType
        from app.models.game.ship import ShipType

        def gates(unit):
            return (unit.value.get('requirements') or {}).get('technologies') or {}

        assert gates(DefenseType.FlackCannon) == {}
        assert gates(ShipType.Fighter) == {}
        for building in (BuildingType.farm, BuildingType.power_station,
                         BuildingType.mater_extractor, BuildingType.rafinery,
                         BuildingType.economical_center, BuildingType.academy):
            assert gates(building) == {}, building.name

    def test_every_unit_requirement_names_a_node_that_exists(self):
        """
        L'invariant qui manquait : `laser`, `atom`, `chemistry` et `energy`
        etaient reclames par les defenses, et trois d'entre eux ne
        correspondaient a rien.
        """
        from app.models.game.buildings import BuildingType
        from app.models.game.defense import DefenseType
        from app.models.game.ship import ShipType

        names = {node.name for node in TechnologyType}
        for catalogue in (BuildingType, ShipType, DefenseType):
            for unit in catalogue:
                required = (unit.value.get('requirements') or {}).get('technologies') or {}
                assert set(required) <= names, unit.name


class TestNodeEffects:

    def test_a_node_at_zero_gives_nothing(self):
        assert TechnologyType.extraction.modifiers_at(level=0) == []

    def test_a_rank_scales_with_its_level(self):
        one = TechnologyType.extraction.modifiers_at(level=1)[0]
        ten = TechnologyType.extraction.modifiers_at(level=10)[0]

        assert one.percentage == pytest.approx(3)
        assert ten.percentage == pytest.approx(30)

    def test_a_doctrine_gives_nothing_until_a_way_is_chosen(self):
        node = TechnologyType.doctrine_de_flotte

        assert node.modifiers_at(level=1) == []
        assert node.modifiers_at(level=1, choice='essaim')

    def test_a_doctrine_gives_only_the_way_that_was_chosen(self):
        node = TechnologyType.doctrine_de_flotte
        swarm = node.modifiers_at(level=1, choice='essaim')
        line = node.modifiers_at(level=1, choice='ligne')

        speeds = {m.percentage for m in swarm if m.type == ModifierType.Speed}
        assert speeds == {10}
        speeds = {m.percentage for m in line if m.type == ModifierType.Speed}
        assert speeds == {-5}

    def test_an_unknown_way_gives_nothing(self):
        assert TechnologyType.doctrine_de_flotte.modifiers_at(
            level=1, choice='mutinerie') == []

    def test_a_doctrine_without_a_way_announces_nothing(self):
        """
        Montrer les effets de la voie du dessus la ferait passer pour ceux du
        noeud — alors que l'autre voie dit le contraire. Les deux se lisent cote
        a cote, dans `options`, et nulle part ailleurs.
        """
        node = TechnologyType.doctrine_de_flotte

        assert node.effect_labels(level=1) == []
        assert node.effect_labels(level=1, choice='essaim')

    def test_the_sentence_and_the_calculation_agree(self):
        """
        Ce que la fiche annonce vient du meme calcul que ce qui est applique :
        c'est la seule facon qu'elle ne mente pas.
        """
        node = TechnologyType.extraction
        label = node.effect_labels(level=7)[0]
        modifier = node.modifiers_at(level=7)[0]

        assert label['current'] == pytest.approx(modifier.percentage)
        assert label['next'] == pytest.approx(
            node.modifiers_at(level=8)[0].percentage)


class TestResearchDuration:

    def test_without_modifiers_the_curve_stands_alone(self):
        node = TechnologyType.calcul

        assert node.duration(level=3) == pytest.approx(
            node.base_time * node.time_factor ** 3)

    def test_computing_architecture_shortens_every_search(self):
        """
        Le noeud qui se rembourse : il ne reduit pas sa propre duree seulement,
        il reduit celle de tout l'arbre.
        """
        user = a_researcher(levels={'calcul': 10})
        plain = TechnologyType.laser.duration(level=3)

        assert TechnologyType.laser.duration(
            level=3, modifiers=user.modifiers) == pytest.approx(plain * 0.8)

    def test_a_technocrat_researches_faster(self):
        faction = a_faction((
            FactionAdvantageType.TimeReduce,
            FactionAdvantageScope.Technologies,
            {'percentage': -10},
        ))
        user = a_researcher(faction=faction)
        plain = TechnologyType.calcul.duration(level=3)

        assert TechnologyType.calcul.duration(
            level=3, modifiers=user.modifiers) == pytest.approx(plain * 0.9)

    def test_faction_and_research_stack(self):
        """
        Le point de tout le moteur : les deux sources s'empilent dans un seul
        ensemble, et personne n'a plus a se demander laquelle interroger.
        """
        faction = a_faction((
            FactionAdvantageType.TimeReduce,
            FactionAdvantageScope.Technologies,
            {'percentage': -10},
        ))
        user = a_researcher(faction=faction, levels={'calcul': 5})
        plain = TechnologyType.laser.duration(level=0)

        # -10 % de la faction et -10 % des cinq niveaux de calcul : additionnes,
        # pas composes.
        assert TechnologyType.laser.duration(
            level=0, modifiers=user.modifiers) == pytest.approx(plain * 0.8)


class TestProgression:

    def test_a_first_tier_node_is_open_from_the_start(self):
        user = a_researcher()

        assert technology_of(user, TechnologyType.extraction).missing_requirements() == []

    def test_a_named_prerequisite_holds_the_door(self):
        user = a_researcher()
        missing = technology_of(user, TechnologyType.chantiers).missing_requirements()

        assert {m['name'] for m in missing} == {'extraction', 'industrie'}
        assert {m['kind'] for m in missing} == {'technology', 'tier'}

    def test_a_tier_opens_with_the_levels_spent_in_its_branch(self):
        """
        La seule barriere qui ne s'achete pas : elle se traverse. Dix niveaux
        dans l'industrie ouvrent son palier II.
        """
        user = a_researcher(levels={'extraction': 5, 'metallurgie': 5})
        missing = technology_of(user, TechnologyType.chantiers).missing_requirements()

        assert missing == []

    def test_levels_of_another_branch_do_not_open_this_one(self):
        user = a_researcher(levels={'calcul': 15})
        missing = technology_of(user, TechnologyType.chantiers).missing_requirements()

        assert {m['kind'] for m in missing} == {'technology', 'tier'}

    def test_a_prerequisite_may_cross_branches(self):
        """
        `Champ de distorsion` est un noeud d'Energie qui demande de
        l'Information : c'est ce qui fait un graphe et non cinq colonnes.
        """
        assert 'calcul' in TechnologyType.distorsion.requires

    def test_a_branch_total_counts_only_its_own(self):
        user = a_researcher(levels={'extraction': 4, 'calcul': 9})
        totals = Technology.branch_levels(user=user)

        assert totals[Branch.industrie] == 4
        assert totals[Branch.information] == 9
        assert totals[Branch.armement] == 0

    def test_a_maxed_rank_refuses_another_level(self):
        node = TechnologyType.extraction
        user = a_researcher(levels={node.name: node.max_level})

        assert not technology_of(user, node).can_be_increased()

    def test_an_endless_node_is_never_maxed(self):
        node = TechnologyType.forge_stellaire

        assert not node.is_maxed(0)
        assert not node.is_maxed(999)


class TestResearchOrder:

    def a_rich_researcher(self, make_territory, levels=None):
        """
        Un joueur dont les mondes portent de quoi payer n'importe quel premier
        niveau. Les reserves sont posees genereusement : ce qu'on eprouve ici
        est la regle de commande, pas l'equilibrage.
        """
        user = a_researcher(levels=levels)
        user.research = 100000.0
        territory = make_territory(user=user)
        for resource in ResourceType.stocks():
            setattr(territory, resource.name, 500000)
        # Pas d'ajout a `user.territories` : `make_territory(user=...)` pose la
        # relation, et `back_populates` remplit l'autre cote tout seul.
        return user

    def test_the_empire_pools_what_its_worlds_hold(self, make_territory):
        user = self.a_rich_researcher(make_territory)
        second = make_territory(user=user)
        second.id = 2
        second.iron = 1000

        assert user.empire_resources['iron'] == 501000

    def test_data_are_held_by_the_player_and_not_by_a_world(self, make_territory):
        user = self.a_rich_researcher(make_territory)

        assert user.empire_resources['research'] == 100000.0

    def test_an_affordable_node_can_be_ordered(self, make_territory):
        user = self.a_rich_researcher(make_territory)

        assert technology_of(user, TechnologyType.extraction).can_be_increased()

    def test_a_node_out_of_reach_cannot(self, make_territory):
        user = a_researcher()
        user.research = 0.0

        assert not technology_of(user, TechnologyType.extraction).can_be_increased()

    def test_the_refusal_says_why(self, make_territory):
        user = self.a_rich_researcher(make_territory)
        technology = technology_of(user, TechnologyType.chantiers)

        with pytest.raises(ValueError) as refused:
            technology.can_be_increased(raises=True)

        assert 'Extraction assistée' in str(refused.value)

    def test_spending_takes_from_the_richest_world_first(self, make_territory):
        """
        Le seul ordre qui ne vide pas un avant-poste pour une recherche que la
        capitale pouvait payer seule.
        """
        user = a_researcher()
        capital = make_territory(user=user)
        capital.iron = 10000
        outpost = make_territory(user=user)
        outpost.id = 2
        outpost.iron = 100

        user.spend_empire({'iron': 500})

        assert capital.iron == 9500
        assert outpost.iron == 100

    def test_spending_spills_over_when_one_world_is_not_enough(self, make_territory):
        user = a_researcher()
        first = make_territory(user=user)
        first.iron = 300
        second = make_territory(user=user)
        second.id = 2
        second.iron = 200

        user.spend_empire({'iron': 400})

        assert first.iron == 0
        assert second.iron == 100

    def test_a_refund_goes_back_where_it_was_taken(self, make_territory):
        user = a_researcher()
        user.research = 1000.0
        capital = make_territory(user=user)
        capital.iron = 10000

        paid = user.spend_empire({'iron': 1000, 'research': 400})
        user.refund_empire(paid, ratio=0.5)

        assert capital.iron == 9500
        assert user.research == pytest.approx(800)

    def test_data_are_not_taken_from_a_world(self, make_territory):
        user = self.a_rich_researcher(make_territory)
        before = dict(user.territories[0].resources)

        user.spend_empire({'research': 5000})

        assert user.research == 95000.0
        assert user.territories[0].resources == before

    def test_a_doctrine_demands_a_way(self, make_territory):
        user = self.a_rich_researcher(make_territory)
        technology = technology_of(user, TechnologyType.doctrine_de_flotte)

        with pytest.raises(ValueError) as refused:
            technology.increase()

        assert 'Essaim' in str(refused.value)

    def test_a_rank_refuses_one(self, make_territory):
        user = self.a_rich_researcher(make_territory)

        with pytest.raises(ValueError):
            technology_of(user, TechnologyType.extraction).increase(choice='essaim')

    def test_a_granted_level_costs_nothing(self, make_territory):
        """
        `now` monte le niveau sans rien facturer : c'est une faveur — une avance
        de partie, un avantage de faction — pas un achat.
        """
        user = self.a_rich_researcher(make_territory)
        technology = technology_of(user, TechnologyType.extraction)
        reserves = dict(user.empire_resources)

        technology.increase(now=True)

        assert technology.level == 1
        assert user.empire_resources == reserves


class TestSerialization:

    def test_a_node_is_named_as_the_api_expects_to_receive_it(self):
        """
        Le nom serialise doit etre celui qu'on peut renvoyer.
        ---
        `POST /api/technology/<name>` resout le nom par
        `TechnologyType.get_by_name`. La lecture rendait
        'TechnologyType.optical' : le client ne pouvait pas reposter ce qu'il
        avait lu sans retirer le prefixe a la main.
        """
        user = a_researcher()

        assert technology_of(user, TechnologyType.laser).serialize['type'] == 'laser'

    def test_the_update_date_is_the_update_date(self):
        """
        Deux dates identiques rendent la seconde inutile : c'est elle qui dit
        quand un niveau a ete atteint.
        """
        later = MOMENT + timedelta(days=3)
        user = a_researcher()
        technology = technology_of(user, TechnologyType.laser)
        technology.updated_at = later

        assert technology.serialize['updated_at'] == later.isoformat()

    def test_a_card_carries_its_state(self):
        user = a_researcher(levels={'extraction': 3})
        card = technology_of(user, TechnologyType.extraction).serialize

        assert card['state'] == 'owned'
        assert card['level'] == 3
        assert card['branch'] == 'industrie'
        assert card['cost']['research'] > 0
        assert card['duration'] > 0

    def test_a_locked_card_says_what_is_missing(self):
        user = a_researcher()
        card = technology_of(user, TechnologyType.chantiers).serialize

        assert card['state'] == 'locked'
        assert card['missing']

    def test_a_maxed_card_announces_neither_cost_nor_duration(self):
        node = TechnologyType.extraction
        user = a_researcher(levels={node.name: node.max_level})
        card = technology_of(user, node).serialize

        assert card['state'] == 'maxed'
        assert 'cost' not in card
        assert 'duration' not in card

    def test_the_catalogue_carries_every_node_and_every_branch(self):
        catalogue = tree()

        assert len(catalogue['nodes']) == len(list(TechnologyType))
        assert len(catalogue['branches']) == len(list(Branch))
        assert catalogue['tiers'] == TIER_REQUIREMENTS

    def test_the_catalogue_survives_json(self):
        """
        Il traverse deux clients : rien de ce qu'il porte ne doit etre un enum
        ni un lambda.
        """
        import json

        assert json.dumps(tree())


class TestRequirementLinks:
    """
    Les deux interfaces font des prerequis un LIEN vers le noeud. Il leur faut
    donc trois choses que le serveur seul peut donner : une liste indexee —
    `JsonUtility` ne lit pas un objet aux cles inconnues —, le libelle a
    afficher, et le nom brut qui sert de cible.
    """

    def test_a_requirement_carries_its_label_and_its_target(self):
        from app.models.game.buildings import BuildingType
        from app.models.game.technologies.technology_type import (
            technology_requirements)

        found = technology_requirements(BuildingType.factory)

        assert found == [{
            'name': 'chantiers',
            'label': TechnologyType.chantiers.label,
            'level': 1,
        }]

    def test_a_unit_that_asks_for_nothing_gets_an_empty_list(self):
        from app.models.game.buildings import BuildingType
        from app.models.game.technologies.technology_type import (
            technology_requirements)

        assert technology_requirements(BuildingType.farm) == []

    def test_every_requirement_target_is_a_node_of_the_tree(self):
        """
        Le nom brut est ce sur quoi l'interface ouvre la vue recherche. S'il ne
        designait aucun noeud, le lien menerait nulle part — en silence, parce
        qu'un client ne peut pas distinguer « noeud inconnu » de « pas encore
        charge ».
        """
        from app.models.game.buildings import BuildingType
        from app.models.game.defense import DefenseType
        from app.models.game.ship import ShipType
        from app.models.game.technologies.technology_type import (
            technology_requirements)

        names = {node.name for node in TechnologyType}
        for catalogue in (BuildingType, ShipType, DefenseType):
            for unit in catalogue:
                for entry in technology_requirements(unit):
                    assert entry['name'] in names, (unit.name, entry['name'])
                    assert entry['label'], (unit.name, entry['name'])
