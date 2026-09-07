# -*- coding: utf-8 -*-

"""
Les outils poses sur la base declarative, et les arguments des evenements.

`app/models/base.py` greffe trois methodes sur tous les modeles du jeu :
`as_dict`, `compare` et `__repr__`. Elles ne relevent d'aucun modele en
particulier, ce qui fait qu'aucun test de modele ne les regarde -- et qu'elles
sont pourtant appelees partout, `as_dict` notamment dans chaque ligne de journal
d'echec de verification.

Le second sujet du fichier tient a la meme raison : les arguments d'un evenement
passent par un `synonym` SQLAlchemy, c'est-a-dire une colonne de texte deguisee
en dictionnaire. La conversion se fait a l'affectation et a la lecture, sans que
rien n'ait besoin d'une base -- et c'est elle qui porte tout ce qu'un chantier
sait de lui-meme : le type commande, la quantite restante, la flotte qui
recevra les vaisseaux.
"""

import json
from datetime import datetime, timedelta

import pytest

from app.models.base import get_check_path
from app.models.game.event import (
    PositionalEvent, PositionalEventType, UserEvent, UserEventType)
from app.models.game.galaxy import Galaxy
from app.models.game.ship import Ship, ShipType


MOMENT = datetime(2026, 1, 1, 12, 0, 0)


class TestAsDict:

    def test_a_model_gives_back_its_columns(self):
        galaxy = Galaxy(name="Voie Lactee", sector_number=12)

        assert galaxy.as_dict() == {
            'name': "Voie Lactee",
            'sector_number': 12,
            'properties': json.dumps(None),
            'created_at': None,
            'updated_at': None,
        }

    def test_to_dict_is_the_same_thing_under_another_name(self):
        """
        Les deux noms coexistent le temps que les modeles s'accordent.
        """
        galaxy = Galaxy(name="Voie Lactee")

        assert galaxy.to_dict() == galaxy.as_dict()


class TestCompare:

    def test_two_identical_rows_have_nothing_to_say(self):
        """
        Aucune difference rend None, et non un dictionnaire vide.
        ---
        L'appelant peut donc ecrire `if difference:` sans avoir a distinguer
        « rien n'a change » de « voici les changements ».
        """
        assert Galaxy(name="Alpha").compare(Galaxy(name="Alpha")) is None

    def test_a_difference_is_reported_both_ways(self):
        before = Galaxy(name="Alpha", sector_number=10)
        after = Galaxy(name="Alpha", sector_number=20)

        assert after.compare(before) == {
            'sector_number': {'new_value': 20, 'original_value': 10},
        }

    def test_the_comparison_can_be_narrowed_to_a_few_columns(self):
        before = Galaxy(name="Alpha", sector_number=10)
        after = Galaxy(name="Beta", sector_number=20)

        assert set(after.compare(before)) == {'name', 'sector_number'}
        assert set(after.compare(before, attrs=['name'])) == {'name'}

    def test_columns_can_be_left_out_instead(self):
        before = Galaxy(name="Alpha", sector_number=10)
        after = Galaxy(name="Beta", sector_number=20)

        assert set(after.compare(
            before, exclude_attrs=['sector_number'])) == {'name'}

    def test_comparing_two_different_things_is_refused(self):
        """
        Un refus net plutot qu'une comparaison qui ne veut rien dire.
        ---
        Les colonnes seraient cherchees sur le mauvais modele : l'erreur
        remonterait de toute facon, mais en `AttributeError` sur une ligne
        interne, sans dire ce qu'on a compare a quoi.
        """
        with pytest.raises(TypeError, match="different type"):
            Galaxy(name="Alpha").compare(Ship(fleet_id=1, type=ShipType.Fighter))


class TestRepr:

    def test_a_model_names_itself_by_its_identifier(self):
        ship = Ship(fleet_id=1, type=ShipType.Fighter)
        ship.id = 12

        assert repr(ship) == "<Ship#12>"

    def test_a_row_never_written_says_so(self):
        """
        L'identifiant est pose par la base : il vaut None avant l'ecriture.
        ---
        C'est justement dans ce moment-la qu'on lit un `repr`, dans un journal
        ou un point d'arret ; il ne doit pas lever.
        """
        assert repr(Ship(fleet_id=1, type=ShipType.Fighter)) == "<Ship#None>"


class TestCheckPath:

    def test_the_checks_of_a_model_live_beside_it(self):
        """
        La convention qui relie un modele a ses verifications.
        ---
        `is_valid` importe ce chemin et ne se plaint pas s'il n'existe pas :
        un modele sans verifications est valide. C'est commode, mais cela veut
        dire qu'une erreur de convention ici ne se signalerait jamais -- d'ou ce
        test, qui la fixe.
        """
        assert get_check_path('app.models.game.territory') == \
            'app.models.checks.game.territory_checks'
        assert get_check_path('app.models.user') == \
            'app.models.checks.user_checks'


class TestEventArguments:

    def a_user_event(self, extra_args):
        return UserEvent(
            user_id=1,
            finishing_at=MOMENT,
            event_type=UserEventType.message,
            extra_args=extra_args,
        )

    def test_a_dictionary_survives_the_round_trip(self, stub):
        """
        Ce qu'un chantier sait de lui-meme tient dans ces arguments.
        ---
        Le type commande, la quantite restante, la duree unitaire, la flotte
        retenue : la colonne est du texte, et c'est le synonyme qui rend un
        dictionnaire des deux cotes.
        """
        args = {'name': 'Fighter', 'quantity': 6, 'unitaryDuration': 48.0}

        event = self.a_user_event(args)

        assert event.extra_args == args
        assert json.loads(event._extra_args) == args

    def test_text_already_encoded_is_taken_as_is(self):
        """
        Une chaine arrive telle quelle depuis la base, sans double encodage.
        """
        event = self.a_user_event(json.dumps({'name': 'Cruiser'}))

        assert event.extra_args == {'name': 'Cruiser'}

    @pytest.mark.parametrize("value", [None, 12, ['Fighter'], object()])
    def test_anything_else_is_refused_at_the_door(self, value):
        """
        Le refus a l'affectation, et non a la lecture.
        ---
        Une valeur illisible ecrite en base ne se signalerait qu'a la relecture
        de l'evenement, c'est-a-dire longtemps apres, et depuis un autre
        appel -- au moment ou le chantier doit livrer.
        """
        with pytest.raises(TypeError, match="Expected str or dict"):
            self.a_user_event(value)

    def test_the_same_rule_holds_for_a_positional_event(self, stub):
        event = PositionalEvent(
            territory=stub(id=7),
            user_id=1,
            finishing_at=MOMENT,
            event_type=PositionalEventType.ship,
            extra_args={'name': 'Fighter', 'quantity': 2},
        )

        assert event.on_territory_id == 7
        assert event.extra_args == {'name': 'Fighter', 'quantity': 2}

        with pytest.raises(TypeError):
            event.extra_args = 42

    def test_arguments_can_be_amended_along_the_way(self, stub):
        """
        Une commande de dix vaisseaux est livree au fil des heures.
        ---
        La quantite restante et la flotte retenue sont reecrites a chaque
        livraison : sans reaffectation possible, dix vaisseaux creeraient dix
        flottes.
        """
        event = PositionalEvent(
            territory=stub(id=7),
            user_id=1,
            finishing_at=MOMENT,
            event_type=PositionalEventType.ship,
            extra_args={'quantity': 10},
        )

        args = event.extra_args
        args['quantity'] = 4
        args['fleetId'] = 3
        event.extra_args = args

        assert event.extra_args == {'quantity': 4, 'fleetId': 3}


class TestEventNaming:

    def test_an_event_type_is_named_without_its_class(self):
        """
        Le prefixe de classe n'apparie aucun champ cote client.
        ---
        `eventType` etait serialise 'PositionalEventType.building' : le client
        devait retirer le prefixe a la main pour savoir de quoi il s'agissait.
        """
        assert str(PositionalEventType.building) == 'building'
        assert str(PositionalEventType.ship) == 'ship'

    def test_archiving_stamps_the_moment_it_happened(self, stub):
        event = PositionalEvent(
            territory=stub(id=7),
            user_id=1,
            finishing_at=MOMENT,
            event_type=PositionalEventType.building,
            extra_args={},
        )
        assert event.archived_at is None

        event.archive()

        assert event.archived_at is not None
        assert event.archived_at - datetime.utcnow() < timedelta(seconds=5)
