"""empty message

Revision ID: 04a2c6872769
Revises: 
Create Date: 2020-02-26 14:37:15.913602

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '04a2c6872769'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        'users',
        sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('users_id_seq'::regclass)"),
                  autoincrement=True, nullable=False),
        sa.Column('username', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('password', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name='users_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table(
        'galaxy',
        sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('sector_number', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('sector_size', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('name', name='galaxy_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table(
        'sector',
        sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('sector_id_seq'::regclass)"),
                  autoincrement=True, nullable=False),
        sa.Column('name', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('galaxy_name', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('position', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['galaxy_name'], ['galaxy.name'], name='sector_galaxy_name_fkey'),
        sa.PrimaryKeyConstraint('id', name='sector_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table(
        'system',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('sector_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['sector_id'], ['sector.id'], name='system_sector_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='system_pkey')
    )
    op.create_table(
        'territory',
        sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('territory_id_seq'::regclass)"),
                  autoincrement=True, nullable=False),
        sa.Column('system_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['system.id'], name='territory_system_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='territory_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table(
        'positional_event',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('on_territory_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['on_territory_id'], ['territory.id'],
                                name='positional_event_on_territory_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='positional_event_pkey')
    )
    op.create_table(
        'event_detail',
        sa.Column('event_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('territory_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('extra_data', sa.VARCHAR(length=2500), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['positional_event.id'], name='event_detail_event_id_fkey'),
        sa.ForeignKeyConstraint(['territory_id'], ['territory.id'], name='event_detail_territory_id_fkey'),
        sa.PrimaryKeyConstraint('event_id', 'territory_id', name='event_detail_pkey')
    )
    op.create_table(
        'user_roles',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('role_type', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('scope', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('deleted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='user_roles_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='user_roles_pkey')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('event_detail')
    op.drop_table('positional_event')
    op.drop_table('territory')
    op.drop_table('system')
    op.drop_table('sector')
    op.drop_table('galaxy')
    # ### end Alembic commands ###