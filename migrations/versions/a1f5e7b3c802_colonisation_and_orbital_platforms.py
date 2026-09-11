# -*- coding: utf-8 -*-

"""La colonisation, et les plateformes orbitales.

Trois colonnes sur le territoire, et deux batiments a poser sur les mondes
qui existent deja.

Le detail qui compte : les lignes de `territory_buildings` sont creees une par
type a la naissance du territoire. Deux types ajoutes au jeu n'existent donc
sur aucun monde deja cree, et la premiere lecture d'un de ces mondes levait un
`StopIteration` nu. On les pose ici pour tout le monde. (`Territory.get_building`
sait desormais se reparer aussi, mais une base propre vaut mieux qu'un filet.)

Le tampon de capitale, ensuite. L'isolement se mesurera en chemin jusqu'a la
capitale : un joueur qui n'en aurait pas verrait tous ses mondes declares
coupes. On designe donc, pour chaque joueur et chaque galaxie, le plus ancien
territoire qu'il y tient.

Revision ID: a1f5e7b3c802
Revises: 9d3f80c1ab42
Create Date: 2026-09-11

"""
import sqlalchemy as sa
from alembic import op


revision = 'a1f5e7b3c802'
down_revision = '9d3f80c1ab42'
branch_labels = None
depends_on = None


#: Les deux batiments neufs. Le nom est celui du membre de `BuildingType` :
#: c'est ce que SQLAlchemy ecrit dans la colonne `Enum`.
NEW_BUILDINGS = ('depot', 'gas_cracker')

#: Les deux coques neuves, membres de `ShipType`.
NEW_SHIPS = ('ColonyShip', 'ExtractionPlatform')


def _widen_enums():
    """
    Apprend les nouvelles valeurs aux types enumeres de PostgreSQL.

    Un `Enum` SQLAlchemy devient un vrai type PostgreSQL, ferme : ajouter un
    membre au cote Python ne suffit pas, et la premiere ecriture echoue sur
    « invalid input value for enum ». Cela ne se voit contre aucune base
    SQLite — les tests montent leur schema par `create_all`, qui recree le type
    entier — et seulement contre un vrai PostgreSQL.

    `autocommit_block` parce que PostgreSQL refuse d'UTILISER une valeur
    ajoutee dans la transaction qui l'ajoute : l'ALTER doit etre valide avant
    que les insertions plus bas ne s'en servent.
    """
    if op.get_bind().dialect.name != 'postgresql':
        return

    with op.get_context().autocommit_block():
        for name in NEW_BUILDINGS:
            op.execute(
                "ALTER TYPE buildingtype ADD VALUE IF NOT EXISTS '%s'" % name)
        for name in NEW_SHIPS:
            op.execute(
                "ALTER TYPE shiptype ADD VALUE IF NOT EXISTS '%s'" % name)


def upgrade():
    _widen_enums()

    # `server_default` et non un simple `default` : la valeur par defaut de
    # SQLAlchemy est posee a l'insertion, en Python. Les lignes deja en base
    # n'en verraient rien et la colonne NOT NULL refuserait de se creer.
    op.add_column('territory', sa.Column(
        'orbital', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('territory', sa.Column(
        'is_capital', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('territory', sa.Column(
        'unstable_since', sa.DateTime(), nullable=True))

    connection = op.get_bind()

    # ── Les batiments manquants ─────────────────────────────────────────────
    for name in NEW_BUILDINGS:
        # `CURRENT_TIMESTAMP` dans le SQL, et non un parametre : une fonction
        # SQLAlchemy passee en valeur liee serait envoyee comme donnee, et le
        # moteur refuserait de l'ecrire dans une colonne de date.
        connection.execute(sa.text("""
            INSERT INTO territory_buildings (type, level, territory_id,
                                             created_at, updated_at)
            SELECT :name, 0, t.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM territory t
            WHERE NOT EXISTS (
                SELECT 1 FROM territory_buildings b
                WHERE b.territory_id = t.id AND b.type = :name
            )
        """), {"name": name})

    # ── La capitale de chacun, dans chaque galaxie ──────────────────────────
    #
    # Le plus ancien territoire tenu : c'est celui par lequel le joueur est
    # entre dans la galaxie. La jointure passe par le systeme, seul porteur du
    # nom de galaxie.
    connection.execute(sa.text("""
        UPDATE territory SET is_capital = TRUE
        WHERE id IN (
            SELECT MIN(t.id)
            FROM territory t
            JOIN system s ON s.id = t.system_id
            WHERE t.user_id IS NOT NULL
            GROUP BY t.user_id, s.galaxy_name
        )
    """))


def downgrade():
    connection = op.get_bind()
    for name in NEW_BUILDINGS:
        connection.execute(
            sa.text("DELETE FROM territory_buildings WHERE type = :name"),
            {"name": name})
    for name in NEW_SHIPS:
        connection.execute(
            sa.text("DELETE FROM ship WHERE type = :name"), {"name": name})

    op.drop_column('territory', 'unstable_since')
    op.drop_column('territory', 'is_capital')
    op.drop_column('territory', 'orbital')

    # Les valeurs ajoutees aux types enumeres RESTENT. PostgreSQL ne sait pas
    # retirer un membre d'un enum autrement qu'en recreant le type et toutes
    # les colonnes qui s'en servent — un travail sans commune mesure avec ce
    # qu'il evite, pour des valeurs que plus aucune ligne ne porte.
