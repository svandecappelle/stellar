"""Split mater into per-material resources and add planet archetypes

Revision ID: b7d1c4e92a10
Revises: 04a2c6872769
Create Date: 2026-09-04

The running stack builds its schema with `Base.metadata.create_all` (see
`initialize.py`), so a fresh database already comes out with these columns.
This migration exists for databases that already hold territories: it is
written defensively and skips whatever is already in place.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7d1c4e92a10'
down_revision = '04a2c6872769'
branch_labels = None
depends_on = None

MATERIALS = (
    ('iron', 10000),
    ('carbon', 4000),
    ('silicium', 2500),
    ('titanium', 0),
    ('cristal', 0),
    ('uranium', 0),
    ('hydrogen', 0),
    ('neutronium', 0),
)

ARCHETYPES = (
    'telluric', 'volcanic', 'oceanic', 'desert', 'ice',
    'gas_giant', 'asteroid', 'irradiated', 'anomaly',
)

#: How the old generic stock is spread over the bulk materials.
MATER_SPLIT = {'iron': 0.55, 'carbon': 0.25, 'silicium': 0.20}


def _columns(bind):
    return {c['name'] for c in sa.inspect(bind).get_columns('territory')}


def upgrade():
    bind = op.get_bind()
    existing = _columns(bind)

    archetype_enum = sa.Enum(*ARCHETYPES, name='planetarchetype')
    archetype_enum.create(bind, checkfirst=True)

    for name, default in MATERIALS:
        if name not in existing:
            op.add_column(
                'territory',
                sa.Column(name, sa.Integer(), nullable=False,
                          server_default=sa.text(str(default))),
            )

    if 'archetype' not in existing:
        op.add_column('territory', sa.Column('archetype', archetype_enum, nullable=True))
    if 'deposits' not in existing:
        op.add_column('territory', sa.Column('deposits', sa.JSON(), nullable=True))

    # Existing worlds become telluric: the archetype is what decides extraction,
    # and telluric is the neutral one. Deposits stay NULL, read as 1.0.
    op.execute("UPDATE territory SET archetype = 'telluric' WHERE archetype IS NULL")

    # Carry the old generic stock over rather than dropping player progress.
    if 'mater' in existing:
        for material, share in MATER_SPLIT.items():
            op.execute(
                "UPDATE territory SET %s = CAST(mater * %s AS INTEGER) WHERE mater > 0"
                % (material, share)
            )
        op.drop_column('territory', 'mater')


def downgrade():
    bind = op.get_bind()
    existing = _columns(bind)

    if 'mater' not in existing:
        op.add_column(
            'territory',
            sa.Column('mater', sa.Integer(), nullable=False, server_default=sa.text('10000')),
        )
        op.execute("UPDATE territory SET mater = iron + carbon + silicium")

    for name, _default in MATERIALS:
        if name in existing:
            op.drop_column('territory', name)
    if 'deposits' in existing:
        op.drop_column('territory', 'deposits')
    if 'archetype' in existing:
        op.drop_column('territory', 'archetype')

    sa.Enum(name='planetarchetype').drop(bind, checkfirst=True)
