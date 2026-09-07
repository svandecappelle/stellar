# -*- coding: utf-8 -*-

"""
Ou en est le schema de la base, face aux migrations du depot.

Deux revisions a rapprocher : celle que la base porte dans `alembic_version`, et
la tete de la chaine de migrations sous `migrations/versions`. Quand elles
different, le code tourne sur un schema qui n'est pas le sien, et cela ne se
voit qu'au premier acces a une colonne absente — c'est-a-dire en pleine partie.
Mieux vaut le dire au demarrage.

Un mot sur ce que ces migrations peuvent et ne peuvent pas faire. Elles font
evoluer une base existante, elles ne la creent pas : la premiere de la chaine
(`04a2c6872769`) est un export automatique de 2020 qui decrit un tout autre
schema — une table `sector`, un `system.sector_id` — que les modeles n'ont plus
depuis longtemps. Une base neuve sort donc de `Base.metadata.create_all`, et
`initialize.py` la tamponne aussitot a la tete pour que la chaine reprenne la
main a partir de la. Rejouer la chaine depuis le debut ne reconstruirait pas ce
schema-ci, cela en batirait un obsolete.
"""

import os

from logger import get_logger

#: Repertoire des migrations, a la racine du depot comme `alembic.ini`.
MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'migrations')


# -- etats possibles -----------------------------------------------------------

#: La base est a la tete : rien a faire.
UP_TO_DATE = 'up_to_date'

#: La base est en retard sur les migrations du depot.
BEHIND = 'behind'

#: La base porte une revision que le depot ne connait pas — code plus ancien
#: que la base, typiquement un retour en arriere sans `downgrade`.
AHEAD = 'ahead'

#: Des tables, mais pas de `alembic_version` : la base n'est pas sous controle
#: de migration. C'est l'etat des bases creees avant que `initialize.py` ne
#: tamponne.
UNSTAMPED = 'unstamped'

#: Base vide, ou illisible. Rien a signaler.
UNKNOWN = 'unknown'


def head_revision():
    """
    La tete de la chaine de migrations, telle que le depot la porte.
    ---
    Lue par alembic lui-meme plutot qu'en relisant les fichiers a la main : il
    sait resoudre les branches et les fusions, ce qu'une lecture de `revision =`
    ligne a ligne ne saurait pas faire.
    """
    try:
        from alembic.script import ScriptDirectory
        return ScriptDirectory(MIGRATIONS_DIR).get_current_head()
    except Exception as e:  # pragma: no cover - depend de l'installation
        get_logger().warn(
            "Cannot read the migration head, schema check skipped",
            infos=dict(error=str(e)))
        return None


def database_revision(engine):
    """
    La revision que la base declare, None si elle n'en declare aucune.
    ---
    Lue directement dans `alembic_version` : passer par l'API d'alembic
    demanderait un contexte de migration, donc une application Flask montee, et
    ce controle doit pouvoir tourner avant elle.
    """
    inspector_tables = _tables(engine)
    if 'alembic_version' not in inspector_tables:
        return None
    try:
        # `engine.execute` a disparu en SQLAlchemy 2.0 : la lecture passe par une
        # connexion explicite. Sans cela le controle tombait dans son propre
        # filet et rendait « revision inconnue » a chaque demarrage — un
        # avertissement de schema en retard qui ne se declenchait plus jamais.
        from sqlalchemy import text

        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None
    except Exception as e:  # pragma: no cover
        get_logger().warn(
            "Cannot read alembic_version", infos=dict(error=str(e)))
        return None


def _tables(engine):
    from sqlalchemy import inspect
    try:
        return set(inspect(engine).get_table_names())
    except Exception:  # pragma: no cover
        return set()


def status(engine):
    """
    Rapproche les deux revisions.
    ---
    :return: (etat, revision de la base, tete du depot)
    """
    head = head_revision()
    if head is None:
        return UNKNOWN, None, None

    current = database_revision(engine)
    if current == head:
        return UP_TO_DATE, current, head

    if current is None:
        # Une base vide n'a rien a migrer : c'est `create_all` qui la batira, et
        # le tampon suivra. Une base qui porte deja des tables, en revanche, est
        # hors de tout controle de version et le silence serait trompeur.
        tables = _tables(engine)
        if not tables:
            return UNKNOWN, None, head
        return UNSTAMPED, None, head

    known = _known_revisions()
    if known and current not in known:
        return AHEAD, current, head

    return BEHIND, current, head


def _known_revisions():
    try:
        from alembic.script import ScriptDirectory
        scripts = ScriptDirectory(MIGRATIONS_DIR)
        return {s.revision for s in scripts.walk_revisions()}
    except Exception:  # pragma: no cover
        return set()


def warn_if_outdated(engine, command="docker compose --profile migrate run --rm migrate"):
    """
    Journalise un avertissement quand le schema n'est pas a la tete.
    ---
    Un avertissement, et non un arret : refuser de demarrer sur un schema en
    retard rendrait la base inatteignable au moment precis ou l'on veut s'y
    connecter pour la reparer. Le message porte la commande a lancer.

    :return: l'etat, pour que l'appelant en fasse ce qu'il veut
    """
    state, current, head = status(engine)

    if state == UP_TO_DATE:
        get_logger().info(
            "Database schema is up to date", infos=dict(revision=head))
        return state

    if state == UNKNOWN:
        return state

    logger = get_logger()
    if state == BEHIND:
        logger.warn(
            "DATABASE SCHEMA IS OUT OF DATE: the database is at revision %s, "
            "the code expects %s. Run the migration before playing, or the "
            "first access to a new column will fail: %s"
            % (current, head, command),
            infos=dict(revision=current, expected=head, command=command))
    elif state == AHEAD:
        logger.warn(
            "DATABASE SCHEMA IS UNKNOWN TO THIS CODE: the database is at "
            "revision %s, which this checkout does not carry. It was migrated "
            "by a newer version — update the code rather than the database."
            % current,
            infos=dict(revision=current, expected=head))
    elif state == UNSTAMPED:
        logger.warn(
            "DATABASE SCHEMA IS NOT UNDER MIGRATION CONTROL: tables are there "
            "but alembic_version is missing, so no migration can tell what is "
            "already applied. Stamp it at the revision matching its schema "
            "(`python manage.py db stamp <revision>`), then run %s"
            % command,
            infos=dict(expected=head, command=command))

    return state
