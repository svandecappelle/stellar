# -*- coding: utf-8 -*-

"""Les jetons d'appareil.

La table qui permet a un joueur de ne plus retaper son mot de passe a chaque
demarrage du jeu. Une ligne par appareil : on n'y range que l'EMPREINTE du
jeton, jamais sa valeur — un vol de la base ne rend donc aucun jeton
utilisable, exactement comme pour les mots de passe.

Rien a faire sur les comptes existants : ils n'ont simplement aucun appareil
enregistre, et en enregistreront un a leur prochaine connexion.

Revision ID: 7c4e2a91f083
Revises: 3ab7d1f65c92
Create Date: 2026-09-10

"""
import sqlalchemy as sa
from alembic import op


revision = '7c4e2a91f083'
down_revision = '3ab7d1f65c92'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        # Soixante-quatre caracteres : la taille d'un SHA-256 en hexadecimal.
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        # Non nul : un jeton sans echeance serait un jeton pour toujours, et
        # c'est precisement ce qu'on ne voulait pas du cookie de memorisation.
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Unique, et pas seulement indexe : deux jetons de meme empreinte seraient
    # deux comptes ouverts par la meme valeur. La probabilite est nulle en
    # pratique — 256 bits de hasard — mais une contrainte coute moins cher a
    # poser qu'a regretter.
    op.create_index(
        'ix_user_tokens_digest', 'user_tokens', ['digest'], unique=True)

    # La liste des appareils d'un compte se lit a chaque ouverture de session.
    op.create_index(
        'ix_user_tokens_user_id', 'user_tokens', ['user_id'], unique=False)


def downgrade():
    op.drop_index('ix_user_tokens_user_id', table_name='user_tokens')
    op.drop_index('ix_user_tokens_digest', table_name='user_tokens')
    op.drop_table('user_tokens')
