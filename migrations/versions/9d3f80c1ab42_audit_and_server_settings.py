# -*- coding: utf-8 -*-

"""Le journal d'audit, et les reglages du serveur.

Deux tables sans lien entre elles, dans la meme revision parce qu'elles
arrivent avec la meme fonctionnalite — la vue d'administration — et qu'un
operateur n'a aucune raison de pouvoir appliquer l'une sans l'autre.

`audit_log` porte ce que les joueurs ont demande et ce que le serveur a
repondu. Elle n'a pas de contrainte d'unicite : c'est un journal, les lignes se
repetent, et la seule chose qui compte est de pouvoir les relire vite — d'ou
les trois index.

`server_settings` n'aura jamais qu'une ligne. Une table pour une ligne surprend,
mais c'est ce qui permet d'ajouter un reglage sans migration : la colonne est
un JSON, et ajouter une cle est alors une modification de code.

Rien a faire sur les donnees existantes : les deux tables naissent vides, et un
serveur sans ligne de reglages se comporte exactement comme avant.

Revision ID: 9d3f80c1ab42
Revises: 7c4e2a91f083
Create Date: 2026-09-11

"""
import sqlalchemy as sa
from alembic import op


revision = '9d3f80c1ab42'
down_revision = '7c4e2a91f083'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        # Nul pour une demande anonyme — une connexion ratee en est une, et
        # c'est precisement celle qu'on veut voir.
        sa.Column('user_id', sa.Integer(), nullable=True),
        # Recopie plutot que jointe : un compte peut disparaitre, la trace de ce
        # qu'il a fait doit lui survivre. C'est aussi le nom ESSAYE lors d'une
        # connexion ratee, qui ne correspond a aucun compte.
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('status', sa.Integer(), nullable=True),
        sa.Column('route', sa.String(length=255), nullable=True),
        sa.Column('address', sa.String(length=64), nullable=True),
        sa.Column('details', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Le journal se lit presque toujours du plus recent : sans cet index, chaque
    # ouverture de la vue trierait la table entiere.
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])
    # « tout ce qu'a fait ce joueur » est la question qui suit toujours la
    # premiere.
    op.create_index('ix_audit_log_user_id', 'audit_log', ['user_id'])
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])

    op.create_table(
        'server_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        # Uniquement ce qui differe du defaut. Un serveur remis a zero n'a plus
        # de ligne du tout.
        sa.Column('overrides', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('server_settings')

    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_index('ix_audit_log_user_id', table_name='audit_log')
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_table('audit_log')
