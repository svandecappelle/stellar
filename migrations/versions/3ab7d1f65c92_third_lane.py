"""Add a third lane to every branch of the technology tree

Revision ID: 3ab7d1f65c92
Revises: f21c6b9e04d7
Create Date: 2026-09-07

L'arbre passe de 90 a 130 noeuds. Rien ne change de forme : c'est le meme type
enum qui accepte quarante noms de plus, et les memes lignes qui se multiplient.

Chaque branche recoit une troisieme voie de huit noeuds, dont une doctrine pour
les deux branches qui n'en avaient pas — Energie et Biosphere. Les seuils de
palier montent dans le code, pas en base : ils ne sont stockes nulle part.

Ecrite defensivement, comme celles qui la precedent : elle declare les noms qui
manquent et insere les lignes qui manquent. Rejouable sans dommage.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3ab7d1f65c92'
down_revision = 'f21c6b9e04d7'
branch_labels = None
depends_on = None


#: Les quarante noeuds ajoutes par cette revision. Recopies plutot
#: qu'importes : une migration decrit l'etat vers lequel elle mene, pas celui
#: que le code aura le jour ou on la rejouera.
ADDED = [
    'outillage', 'moulage_sous_vide', 'robotique_lourde', 'chaines_logistiques',
    'depots_orbitaux', 'impression_moleculaire', 'logistique_quantique', 'desassemblage_planetaire',
    'poussee_chimique', 'dissipateurs', 'refroidissement', 'doctrine_energetique',
    'champs_inertiels', 'accumulateurs_massiques', 'conversion_directe', 'corridor_stable',
    'brouillage', 'leurres', 'sondes_passives', 'piratage',
    'veille_permanente', 'cartographie_profonde', 'dominance_spectrale', 'precognition',
    'habitats_pressurises', 'marches_locaux', 'urbanisme', 'doctrine_sociale',
    'agriculture_orbitale', 'guildes_marchandes', 'medecine_regenerative', 'essaimage',
    'soudure_structurelle', 'focalisation', 'railguns', 'dispersion_thermique',
    'lances_a_particules', 'surcharge_capacitive', 'torpilles_relativistes', 'annihilation',
]


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
    Un COMMIT par valeur, meme precaution que les deux revisions precedentes :
    avant Postgres 12 un `ADD VALUE` ne tourne pas dans un bloc transactionnel,
    et une valeur fraichement ajoutee ne s'emploie qu'une fois sa transaction
    validee — or les insertions qui suivent emploient ces noms.

    SQLite range un enum en VARCHAR : rien a y faire.
    """
    if bind.dialect.name != 'postgresql':
        return

    existing = _enum_labels(bind, type_name)
    if existing is None:
        return

    missing = [value for value in values if value not in existing]
    for value in missing:
        op.execute('COMMIT')
        op.execute("ALTER TYPE %s ADD VALUE '%s'" % (type_name, value))
    if missing:
        op.execute('COMMIT')


def upgrade():
    _add_enum_values(op.get_bind(), 'technologytype', ADDED)

    # Un noeud a zero pour chaque compte qui en possede deja : les comptes sans
    # technologies sont les non jouables, et n'ont pas a en recevoir.
    for node in ADDED:
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
    # Seuls les quarante noeuds de cette revision partent ; les quatre-vingt-dix
    # d'avant, niveaux et voies de doctrine compris, restent tels quels.
    op.execute(
        "DELETE FROM user_technologies WHERE type IN (%s)"
        % ", ".join("'%s'" % node for node in ADDED))

    # Une recherche en cours sur un noeud disparu n'a plus d'objet.
    op.execute(
        "DELETE FROM user_event WHERE event_type = 'research' AND (%s)"
        % " OR ".join(
            "_extra_args LIKE '%%\"type\": \"%s\"%%'" % node
            for node in ADDED))

    # Les valeurs ajoutees aux types enum ne sont pas retirees : Postgres ne
    # sait pas defaire un ADD VALUE, et les laisser en place ne gene rien.
