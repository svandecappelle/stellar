"""Add the food resource, the farm building and territory stability

Revision ID: c3e8f1a54d92
Revises: b7d1c4e92a10
Create Date: 2026-09-05

The running stack builds its schema with `Base.metadata.create_all` (see
`initialize.py`), so a fresh database already comes out with these columns and
every territory already gets its farm row. This migration exists for databases
that already hold territories: like the one before it, it is written
defensively and skips whatever is already in place.

Three things move at once, because they are one mechanic:

  · `food`, a stock like any other, filled by the new farm;
  · `stability`, which the food shortage eats into;
  · a `farm` row on every existing territory — without it an old world has no
    food producer at all, and would starve the moment its reserve runs out.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3e8f1a54d92'
down_revision = 'b7d1c4e92a10'
branch_labels = None
depends_on = None

#: Reserve de depart, alignee sur le defaut du modele.
FOOD_DEFAULT = 1000

#: Un monde deja en jeu n'a pas a payer la nouveaute : il demarre apaise.
STABILITY_DEFAULT = 100


def _columns(bind):
    return {c['name'] for c in sa.inspect(bind).get_columns('territory')}


def _add_farm_to_enum(bind):
    """
    Declare `farm` dans le type enum des batiments.

    Postgres tient un vrai type enum, qui refuse toute valeur non declaree :
    sans ce ALTER, l'insertion des lignes de ferme echouerait. SQLite stocke
    l'enum en VARCHAR avec une contrainte CHECK recreee par `create_all` : il
    n'y a rien a faire, et le dialecte est simplement laisse tranquille.
    """
    if bind.dialect.name != 'postgresql':
        return
    # IF NOT EXISTS rend la migration rejouable ; le ADD VALUE d'un enum ne peut
    # pas tourner dans une transaction sur les Postgres anterieurs a 12, d'ou le
    # COMMIT prealable.
    op.execute('COMMIT')
    op.execute("ALTER TYPE buildingtype ADD VALUE IF NOT EXISTS 'farm'")


def upgrade():
    bind = op.get_bind()
    existing = _columns(bind)

    if 'food' not in existing:
        op.add_column(
            'territory',
            sa.Column('food', sa.Integer(), nullable=False,
                      server_default=sa.text(str(FOOD_DEFAULT))),
        )

    if 'stability' not in existing:
        op.add_column(
            'territory',
            sa.Column('stability', sa.Integer(), nullable=False,
                      server_default=sa.text(str(STABILITY_DEFAULT))),
        )

    _add_farm_to_enum(bind)

    # Une ferme de niveau 0 sur chaque monde qui n'en a pas. Le niveau 0 produit
    # deja un fond de recolte, exactement comme la centrale electrique : le
    # joueur n'a rien a faire pour que sa population continue de manger.
    op.execute(
        """
        INSERT INTO territory_buildings (type, level, territory_id, created_at, updated_at)
        SELECT 'farm', 0, t.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM territory t
        WHERE NOT EXISTS (
            SELECT 1 FROM territory_buildings b
            WHERE b.territory_id = t.id AND b.type = 'farm'
        )
        """
    )


def downgrade():
    bind = op.get_bind()
    existing = _columns(bind)

    op.execute("DELETE FROM territory_buildings WHERE type = 'farm'")

    if 'stability' in existing:
        op.drop_column('territory', 'stability')
    if 'food' in existing:
        op.drop_column('territory', 'food')

    # La valeur `farm` reste dans le type enum : Postgres ne sait pas retirer
    # une valeur d'un enum, et une valeur declaree que personne n'utilise ne
    # gene rien.
