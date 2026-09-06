"""Move ships from territories into fleets

Revision ID: e91b4d70a2f5
Revises: c3e8f1a54d92
Create Date: 2026-09-06

Un vaisseau n'appartient plus a la planete qui l'a assemble. Il sort du
chantier pour l'espace du systeme, ou il fait partie d'une flotte : c'est la
flotte qui porte une position — des coordonnees Unity, gardees telles quelles
pour que le client la retrouve au meme endroit — et l'orbite qu'elle tient.

Trois mouvements, qui n'en font qu'un :

  · la table `fleet` apparait ;
  · `ship_territory` devient `ship`, rattachee a une flotte ;
  · les stocks existants sont verses dans une flotte par territoire, amarree a
    l'orbite de ce territoire. Un joueur retrouve donc ses vaisseaux la ou il
    les avait, en orbite de la planete qui les a produits.

Comme les precedentes, ecrite defensivement : une base fraiche sort deja de
`Base.metadata.create_all` avec le bon schema (voir `initialize.py`), et cette
migration ne concerne que les bases qui portent deja des vaisseaux.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e91b4d70a2f5'
down_revision = 'c3e8f1a54d92'
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


#: Les types de vaisseaux, dans l'ordre de `ShipType`.
SHIP_TYPES = (
    'DefenseSatellite', 'Fighter', 'Interceptor', 'Cruiser', 'Frigate',
    'MotherShip', 'OrbitalStation',
)


def _ship_type(bind):
    """
    Le type SQL de la colonne `type`, sans jamais recreer l'enum.

    Postgres tient un vrai type nomme `shiptype`, deja cree avec
    `ship_territory` : laisser alembic le declarer une seconde fois ferait
    echouer la migration sur un « type already exists ». SQLite n'a pas de type
    enum, il recoit un VARCHAR avec une contrainte CHECK et rien a partager.
    """
    if bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects import postgresql
        return postgresql.ENUM(*SHIP_TYPES, name='shiptype', create_type=False)
    return sa.Enum(*SHIP_TYPES, name='shiptype')


def _create_fleet(bind):
    if 'fleet' in _tables(bind):
        return
    op.create_table(
        'fleet',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('system_id', sa.Integer(), sa.ForeignKey('system.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        # Coordonnees Unity du repere du systeme. Le serveur ne les interprete
        # pas : la geometrie du systeme vit chez le client.
        sa.Column('position_x', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('position_y', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('position_z', sa.Float(), nullable=False, server_default=sa.text('0')),
        # Orbite declaree, jamais deduite d'une distance : c'est elle qui decide
        # a quelle flotte revient un vaisseau qui sort de chantier.
        sa.Column('orbiting_territory_id', sa.Integer(),
                  sa.ForeignKey('territory.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def _create_ship(bind):
    if 'ship' in _tables(bind):
        return
    op.create_table(
        'ship',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', _ship_type(bind), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('fleet_id', sa.Integer(), sa.ForeignKey('fleet.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def _move_stocks(bind):
    """
    Verser les stocks de `ship_territory` dans des flottes.

    Une flotte par territoire qui detient au moins un vaisseau, amarree a
    l'orbite de ce territoire et rendue a son proprietaire. Les lignes a zero
    ne sont pas reprises : chaque territoire en portait sept, une par type,
    creees a vide a sa naissance et que plus rien ne justifie.

    Un territoire sans proprietaire est ignore : une flotte appartient a un
    joueur, et un monde inoccupe ne peut en tenir aucune.
    """
    if 'ship_territory' not in _tables(bind):
        return

    op.execute(
        """
        INSERT INTO fleet (system_id, user_id, name, position_x, position_y,
                           position_z, orbiting_territory_id, created_at, updated_at)
        SELECT t.system_id, t.user_id, 'Fleet 1', 0, 0, 0, t.id,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM territory t
        WHERE t.user_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM ship_territory s
            WHERE s.territory_id = t.id AND s.count > 0
          )
          AND NOT EXISTS (
            SELECT 1 FROM fleet f WHERE f.orbiting_territory_id = t.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO ship (type, count, fleet_id, created_at, updated_at)
        SELECT s.type, s.count, f.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM ship_territory s
        JOIN fleet f ON f.orbiting_territory_id = s.territory_id
        WHERE s.count > 0
        """
    )


def upgrade():
    bind = op.get_bind()
    _create_fleet(bind)
    _create_ship(bind)
    _move_stocks(bind)

    if 'ship_territory' in _tables(bind):
        op.drop_table('ship_territory')


def downgrade():
    bind = op.get_bind()

    if 'ship_territory' not in _tables(bind):
        op.create_table(
            'ship_territory',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('type', _ship_type(bind), nullable=False),
            sa.Column('count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('territory_id', sa.Integer(),
                      sa.ForeignKey('territory.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )

    # Seules les flottes amarrees ont un territoire ou revenir. Ce qui croisait
    # dans le vide n'a pas de place dans un schema ou les vaisseaux pendent a
    # une planete : ce retour en arriere perd ces vaisseaux-la, et c'est
    # inevitable — l'ancien schema n'avait nulle part ou les mettre.
    if 'ship' in _tables(bind):
        op.execute(
            """
            INSERT INTO ship_territory (type, count, territory_id, created_at, updated_at)
            SELECT s.type, s.count, f.orbiting_territory_id,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM ship s
            JOIN fleet f ON f.id = s.fleet_id
            WHERE f.orbiting_territory_id IS NOT NULL
            """
        )
        op.drop_table('ship')

    if 'fleet' in _tables(bind):
        op.drop_table('fleet')
