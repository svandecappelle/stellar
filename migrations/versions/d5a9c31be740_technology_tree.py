"""Replace the flat technology list with the branched technology tree

Revision ID: d5a9c31be740
Revises: a4c7f2b81d63
Create Date: 2026-09-07

La pile en service construit son schema avec `Base.metadata.create_all` (voir
`initialize.py`) : une base neuve sort deja avec les colonnes et les valeurs
d'enum qui suivent. Cette migration existe pour les bases qui portent deja des
comptes, et elle est ecrite defensivement — comme les precedentes, elle passe
sur ce qui est deja en place.

Quatre choses bougent, et elles n'en font qu'une :

  · `users.research`, la reserve de Donnees. La recherche est imperiale, sa
    monnaie ne pouvait pas rester sur un territoire ;
  · `user_technologies.choice`, la voie retenue d'une doctrine ;
  · l'enum des technologies passe de 7 a 36 membres, et les sept anciens sont
    renommes. Un joueur ne perd rien : `computer` devient `calcul` avec son
    niveau ;
  · l'enum des evenements de joueur gagne `research`, et celui des
    modificateurs les trois types et les trois portees qu'ajoute l'arbre.

Les vingt-neuf noeuds nouveaux sont poses a zero pour chaque compte existant.
Sans eux, `Technology.get` leverait sur le premier noeud qu'un joueur voudrait
regarder.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5a9c31be740'
down_revision = 'a4c7f2b81d63'
branch_labels = None
depends_on = None


#: Les sept membres d'avant vers ce qui les remplace. Doit rester le miroir de
#: `LEGACY_NAMES` dans `technology_type.py` : la migration ne peut pas importer
#: le modele, qui aura change avant qu'elle ne tourne.
LEGACY_NAMES = {
    'computer': 'calcul',
    'optical': 'optique',
    'chemistry': 'ogives',
    'alliage': 'alliages',
    'energy': 'fission',
    'atom': 'atomique',
    # `distorsion` garde son nom : rien a renommer.
}

#: Les 36 noeuds, dans l'ordre de la table. Recopies plutot qu'importes, pour
#: la meme raison.
NODES = [
    'extraction', 'metallurgie', 'chantiers', 'raffinage', 'forage',
    'automatisation', 'doctrine_industrielle', 'forge_stellaire',
    'fission', 'supraconducteurs', 'fusion', 'stockage', 'antimatiere',
    'distorsion', 'point_zero',
    'calcul', 'optique', 'reseau_quantique', 'cartographie',
    'intelligence_artificielle', 'guerre_electronique', 'singularite',
    'agronomie', 'medecine', 'bureaucratie', 'adaptation', 'commerce',
    'terraformation', 'ascension',
    'alliages', 'laser', 'ogives', 'boucliers', 'atomique',
    'doctrine_de_flotte', 'coque_neutronium',
]

#: Ce que les nouvelles portees et les nouveaux types ajoutent aux enums de
#: modificateurs. SQLAlchemy ecrit le NOM du membre, pas sa valeur.
MODIFIER_TYPES = ['Capacity', 'Speed', 'Unlock']
MODIFIER_SCOPES = ['Fleet', 'Territory', 'Research']


def _columns(bind, table):
    return {c['name'] for c in sa.inspect(bind).get_columns(table)}


def _enum_labels(bind, type_name):
    """
    Les membres deja declares dans un type enum Postgres, ou None s'il n'existe
    pas — auquel cas la colonne n'est pas un enum natif et il n'y a rien a y
    ajouter.
    """
    rows = bind.execute(sa.text(
        "SELECT e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = :name"
    ), {"name": type_name}).fetchall()
    return {row[0] for row in rows} if rows else None


def _add_enum_values(bind, type_name, values):
    """
    Declarer des membres dans un type enum Postgres.
    ---
    SQLite range un enum en VARCHAR avec une contrainte CHECK que `create_all`
    refait : il n'y a rien a y faire, et le dialecte est laisse tranquille.

    Un COMMIT par valeur, et non un seul avant la boucle. Ce n'est pas une
    correction : la version a COMMIT unique passe sur Postgres 14, verifiee sur
    un clone de la base de production. C'est une precaution, et elle vise deux
    regles du serveur qui ne se voient pas sur cette version-la :

      · avant la 12, `ALTER TYPE ... ADD VALUE` ne peut pas tourner dans un bloc
        transactionnel. Un COMMIT unique ne degage que le premier ajout ;
      · une valeur fraichement ajoutee ne peut pas etre EMPLOYEE tant que sa
        transaction n'est pas validee — et le renommage juste apres emploie
        precisement ces noms-la.

    Les valeurs deja presentes sont filtrees en amont plutot que confiees a
    `IF NOT EXISTS` : la migration reste rejouable meme la ou cette clause n'est
    pas connue, et une base deja a jour ne paie pas trente-six allers-retours
    pour ne rien faire.
    """
    if bind.dialect.name != 'postgresql':
        return

    existing = _enum_labels(bind, type_name)
    if existing is None:
        # Type absent : la colonne n'est pas un enum natif sur cette base, les
        # ordres qui suivent ecriront des chaines et s'en accommoderont.
        return

    missing = [value for value in values if value not in existing]
    for value in missing:
        # Chaque ajout dans sa propre transaction, refermee aussitot.
        op.execute('COMMIT')
        op.execute("ALTER TYPE %s ADD VALUE '%s'" % (type_name, value))
    if missing:
        # Et une derniere, pour que les noms ajoutes soient utilisables par les
        # ordres de donnees qui suivent.
        op.execute('COMMIT')


def upgrade():
    bind = op.get_bind()

    if 'research' not in _columns(bind, 'users'):
        op.add_column(
            'users',
            sa.Column('research', sa.Float(), nullable=False,
                      server_default=sa.text('0')),
        )

    if 'choice' not in _columns(bind, 'user_technologies'):
        op.add_column(
            'user_technologies',
            sa.Column('choice', sa.String(length=50), nullable=True),
        )

    # Les noms d'enum d'abord, les donnees ensuite : le renommage et les
    # insertions plus bas emploient les noms ajoutes ici.
    _add_enum_values(bind, 'technologytype', NODES)
    _add_enum_values(bind, 'usereventtype', ['research'])
    _add_enum_values(bind, 'factionadvantagetype', MODIFIER_TYPES)
    _add_enum_values(bind, 'factionadvantagescope', MODIFIER_SCOPES)

    # Les sept lignes d'avant prennent leur nouveau nom, avec leur niveau. Le
    # renommage se fait ligne par ligne et non par un ALTER TYPE ... RENAME
    # VALUE : ce dernier n'existe qu'a partir de Postgres 10 et ne dirait rien
    # a SQLite.
    for old, new in LEGACY_NAMES.items():
        op.execute(
            "UPDATE user_technologies SET type = '%s' WHERE type = '%s'" % (new, old))

    # Les noeuds qui n'existaient pas, a zero, pour chaque compte deja cree.
    for node in NODES:
        op.execute(
            """
            INSERT INTO user_technologies (type, user_id, level, created_at, updated_at)
            SELECT '{node}', u.id, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM users u
            WHERE EXISTS (
                SELECT 1 FROM user_technologies t WHERE t.user_id = u.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM user_technologies t
                WHERE t.user_id = u.id AND t.type = '{node}'
            )
            """.format(node=node)
        )


def downgrade():
    bind = op.get_bind()

    # Les vingt-neuf noeuds nouveaux disparaissent ; les sept anciens
    # retrouvent leur nom et leur niveau.
    kept = set(LEGACY_NAMES.values()) | {'distorsion'}
    removable = [n for n in NODES if n not in kept]
    if removable:
        op.execute(
            "DELETE FROM user_technologies WHERE type IN (%s)"
            % ", ".join("'%s'" % n for n in removable))

    for old, new in LEGACY_NAMES.items():
        op.execute(
            "UPDATE user_technologies SET type = '%s' WHERE type = '%s'" % (old, new))

    # Une recherche en cours n'a plus de type d'evenement ou aller.
    op.execute("DELETE FROM user_event WHERE event_type = 'research'")

    if 'choice' in _columns(bind, 'user_technologies'):
        op.drop_column('user_technologies', 'choice')
    if 'research' in _columns(bind, 'users'):
        op.drop_column('users', 'research')

    # Les valeurs ajoutees aux types enum ne sont pas retirees : Postgres ne
    # sait pas defaire un ADD VALUE, et les laisser en place ne gene rien.
