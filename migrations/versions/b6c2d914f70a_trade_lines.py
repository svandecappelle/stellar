# -*- coding: utf-8 -*-

"""Les lignes de commerce, et le cargo qui les ouvre.

Une table, et une valeur de plus au type enumere des coques.

Rien a faire sur les mondes existants : une base sans ligne est une base ou
personne n'a encore ouvert de route. Le raccordement, lui, ne s'en trouve pas
casse — deux territoires d'un meme systeme sont relies sans ligne, et la
capitale est raccordee par definition.

Revision ID: b6c2d914f70a
Revises: a1f5e7b3c802
Create Date: 2026-09-11

"""
import sqlalchemy as sa
from alembic import op


revision = 'b6c2d914f70a'
down_revision = 'a1f5e7b3c802'
branch_labels = None
depends_on = None


#: La coque neuve, membre de `ShipType`.
NEW_SHIPS = ('Freighter',)


def _widen_enums():
    """
    Apprend le cargo au type enumere de PostgreSQL.

    Un `Enum` SQLAlchemy devient un vrai type PostgreSQL, ferme. Ajouter un
    membre cote Python ne suffit pas — voir la revision precedente, qui a paye
    cette lecon. `autocommit_block` parce que PostgreSQL refuse d'utiliser une
    valeur ajoutee dans la transaction qui l'ajoute.
    """
    if op.get_bind().dialect.name != 'postgresql':
        return

    with op.get_context().autocommit_block():
        for name in NEW_SHIPS:
            op.execute(
                "ALTER TYPE shiptype ADD VALUE IF NOT EXISTS '%s'" % name)


def upgrade():
    _widen_enums()

    op.create_table(
        'trade_line',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('origin_id', sa.Integer(), nullable=False),
        sa.Column('destination_id', sa.Integer(), nullable=False),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        # Une ligne fermee est GARDEE : elle dit qu'une route a existe, et a
        # quel moment elle a cesse. L'effacer effacerait aussi cette trace.
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        # Les flux declares, en JSON. Une colonne plutot qu'une table : un flux
        # n'a pas d'existence hors de sa ligne, et en ajouter un ne doit pas
        # demander de migration.
        sa.Column('flows', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['origin_id'], ['territory.id'], ),
        sa.ForeignKeyConstraint(['destination_id'], ['territory.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # « Les lignes de ce joueur » est la lecture faite a chaque tour de jeu de
    # chaque monde : c'est elle qui decide du raccordement.
    op.create_index('ix_trade_line_user_id', 'trade_line', ['user_id'])
    op.create_index('ix_trade_line_origin_id', 'trade_line', ['origin_id'])
    op.create_index(
        'ix_trade_line_destination_id', 'trade_line', ['destination_id'])


def downgrade():
    op.drop_index('ix_trade_line_destination_id', table_name='trade_line')
    op.drop_index('ix_trade_line_origin_id', table_name='trade_line')
    op.drop_index('ix_trade_line_user_id', table_name='trade_line')
    op.drop_table('trade_line')

    connection = op.get_bind()
    for name in NEW_SHIPS:
        connection.execute(
            sa.text("DELETE FROM ship WHERE type = :name"), {"name": name})

    # La valeur ajoutee au type enumere reste : PostgreSQL ne sait pas retirer
    # un membre d'un enum autrement qu'en recreant le type et toutes les
    # colonnes qui s'en servent.
