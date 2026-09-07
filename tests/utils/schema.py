# -*- coding: utf-8 -*-

"""
Lecture de la revision de schema.

Ce controle est le seul garde-fou contre une base en retard : il previent, au
demarrage, qu'une colonne attendue par le code n'existe pas encore. Il tombe
donc dans une categorie ingrate — quand il cesse de marcher, rien n'echoue, il
se contente de ne plus rien dire.

C'est exactement ce qui s'est produit au passage a SQLAlchemy 2.0 :
`engine.execute` a disparu, la lecture partait dans son propre filet et rendait
« revision inconnue ». L'avertissement ne s'est plus jamais declenche, et seule
une ligne de journal l'a trahi. D'ou ces tests, qui lisent une vraie base.
"""

from sqlalchemy import create_engine, text

import schema_version


def _engine_with(revision=None, other_tables=False):
    """Une base en memoire, avec ou sans tampon de revision."""
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        if other_tables:
            connection.execute(text("CREATE TABLE territory (id INTEGER)"))
        if revision is not None:
            connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:r)"),
                {"r": revision})
    return engine


class TestSchemaVersion:

    def test_reads_the_revision_the_database_declares(self):
        engine = _engine_with(revision='c0ffee')
        assert schema_version.database_revision(engine) == 'c0ffee'

    def test_a_database_without_stamp_declares_nothing(self):
        assert schema_version.database_revision(_engine_with()) is None

    def test_a_database_at_head_is_up_to_date(self):
        """
        La tete vient du depot : le test suit les migrations sans etre reecrit.
        """
        head = schema_version.head_revision()
        assert head is not None, "les migrations du depot devraient avoir une tete"

        state, current, expected = schema_version.status(_engine_with(revision=head))
        assert state == schema_version.UP_TO_DATE
        assert current == head == expected

    def test_a_database_left_behind_is_seen_as_such(self):
        """
        Le cas qui compte : c'est celui que l'avertissement doit annoncer.
        """
        revisions = list(schema_version._known_revisions())
        head = schema_version.head_revision()
        older = next((r for r in revisions if r != head), None)
        assert older is not None, "il faut au moins deux revisions pour ce test"

        state, current, expected = schema_version.status(_engine_with(revision=older))
        assert state == schema_version.BEHIND
        assert current == older
        assert expected == head

    def test_tables_without_a_stamp_are_out_of_version_control(self):
        """
        Une base vide n'a rien a migrer ; une base peuplee sans tampon, si.
        Les confondre laisserait passer le seul cas ou le silence est trompeur.
        """
        state, _, _ = schema_version.status(_engine_with(other_tables=True))
        assert state == schema_version.UNSTAMPED

        state, _, _ = schema_version.status(_engine_with())
        assert state == schema_version.UNKNOWN
