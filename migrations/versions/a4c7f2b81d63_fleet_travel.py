"""Give fleets a travel state, so they can cross the galaxy star lane by star lane

Revision ID: a4c7f2b81d63
Revises: e91b4d70a2f5
Create Date: 2026-09-06

Until now a fleet belonged to one system and never left it: the only way to
have ships elsewhere was to build them there. Travelling between stars needs
three things remembered, and they are added here.

The running stack builds its schema with `Base.metadata.create_all` (see
`initialize.py`), so a fresh database already comes out with these columns.
This migration is for databases that already hold fleets, and like the ones
before it, it is written defensively: it looks at what is there and adds only
what is missing.

Why three columns rather than a `fleet_travel` table: a fleet has at most one
journey at a time, so a table would never hold more than one row per fleet, and
every read of a fleet would pay a join for a column that is null most of the
time.

Why the route is stored rather than recomputed: it is frozen at departure. A
galaxy that grows during a game — new systems, hence new star lanes — must not
reroute a fleet already under way, and the countdown the player is watching
must not move under them.

No data migration: fleets already in place are simply not travelling, which is
what three null columns say.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a4c7f2b81d63'
down_revision = 'e91b4d70a2f5'
branch_labels = None
depends_on = None


#: Les colonnes ajoutees, dans l'ordre ou elles se lisent : le chemin, la duree
#: de chaque saut, et l'instant du depart. Les trois vont ensemble — une seule
#: d'entre elles ne dit rien.
COLUMNS = (
    ('travel_route', sa.Column('travel_route', sa.String(), nullable=True)),
    ('travel_legs', sa.Column('travel_legs', sa.String(), nullable=True)),
    ('travel_started_at', sa.Column('travel_started_at', sa.DateTime(), nullable=True)),
)


def _existing(bind, table):
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return None
    return {column['name'] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    present = _existing(bind, 'fleet')

    if present is None:
        # Base d'avant les flottes : la migration qui les cree est en amont de
        # celle-ci, et si la table manque encore c'est que la chaine a ete
        # jouee dans le desordre. Rien a faire ici plutot qu'echouer.
        return

    for name, column in COLUMNS:
        if name not in present:
            op.add_column('fleet', column)


def downgrade():
    bind = op.get_bind()
    present = _existing(bind, 'fleet')

    if present is None:
        return

    for name, _ in reversed(COLUMNS):
        if name in present:
            op.drop_column('fleet', name)
