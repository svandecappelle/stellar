"""Deepen the technology tree from four tiers to ten

Revision ID: f21c6b9e04d7
Revises: d5a9c31be740
Create Date: 2026-09-07

L'arbre passe de 36 a 90 noeuds et de quatre paliers a dix. Rien ne change de
forme : la table `user_technologies` porte deja un type, un joueur, un niveau et
une voie. Ce qui change est le nombre de valeurs que le type accepte, et le
nombre de lignes qu'un joueur possede.

Aucun renommage cette fois — les 36 noeuds d'avant existent tous encore, aux
memes noms et aux memes places. Les 54 nouveaux sont poses a zero pour chaque
compte deja cree.

Ecrite defensivement, comme celles qui la precedent : elle declare les noms qui
manquent et insere les lignes qui manquent, et ne fait rien la ou tout est deja
en place. Rejouable sans dommage.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f21c6b9e04d7'
down_revision = 'd5a9c31be740'
branch_labels = None
depends_on = None


#: Les 90 noeuds, dans l'ordre de la table. Recopies plutot qu'importes : une
#: migration doit decrire l'etat vers lequel elle mene, pas celui que le code
#: aura le jour ou on la rejouera.
NODES = [
    'extraction', 'metallurgie', 'chantiers', 'raffinage',
    'forage', 'convoyeurs', 'automatisation', 'metaux_rares',
    'fonderie_orbitale', 'doctrine_industrielle', 'nanofabrication', 'mineurs_autonomes',
    'assemblage_parallele', 'transmutation', 'chaine_fermee', 'exploitation_stellaire',
    'usines_autoreplicantes', 'forge_stellaire', 'fission', 'supraconducteurs',
    'stockage', 'thermique', 'fusion', 'plasma',
    'volants_inertie', 'propulsion_ionique', 'antimatiere', 'distorsion',
    'reacteur_annulaire', 'condensateurs_quantiques', 'moteur_a_saut', 'collecteurs_stellaires',
    'singularite_contenue', 'pliage', 'reacteur_a_vide', 'point_zero',
    'calcul', 'optique', 'algorithmes', 'cartographie',
    'reseau_quantique', 'capteurs_gravimetriques', 'guerre_electronique', 'chiffrement',
    'intelligence_artificielle', 'simulation', 'essaim_de_sondes', 'traitement_massif',
    'contre_mesures', 'reseau_neural', 'calcul_quantique', 'conscience_distribuee',
    'omniscience', 'singularite', 'agronomie', 'medecine',
    'hydroponie', 'bureaucratie', 'adaptation', 'sante_publique',
    'commerce', 'cultures_modifiees', 'arcologies', 'terraformation',
    'banque_centrale', 'symbiotes', 'mondes_jardins', 'longevite',
    'economie_planifiee', 'biosphere_close', 'genese', 'ascension',
    'alliages', 'laser', 'ogives', 'ciblage',
    'boucliers', 'coques_renforcees', 'atomique', 'blindage_composite',
    'artillerie_lourde', 'doctrine_de_flotte', 'champs_modules', 'munitions_denses',
    'coque_ablative', 'canons_gravitiques', 'bouclier_planetaire', 'armement_exotique',
    'titan', 'coque_neutronium',
]

#: Ceux que la revision precedente avait deja poses. Le retour arriere les
#: garde : c'est exactement l'arbre a quatre paliers.
PREVIOUS_NODES = {
    'extraction', 'metallurgie', 'chantiers', 'raffinage', 'forage',
    'automatisation', 'doctrine_industrielle', 'forge_stellaire',
    'fission', 'supraconducteurs', 'fusion', 'stockage', 'antimatiere',
    'distorsion', 'point_zero', 'calcul', 'optique', 'reseau_quantique',
    'cartographie', 'intelligence_artificielle', 'guerre_electronique',
    'singularite', 'agronomie', 'medecine', 'bureaucratie', 'adaptation',
    'commerce', 'terraformation', 'ascension', 'alliages', 'laser',
    'ogives', 'boucliers', 'atomique', 'doctrine_de_flotte',
    'coque_neutronium',
}


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
    Meme precaution que la revision precedente : un COMMIT par valeur, parce
    qu'avant Postgres 12 un `ADD VALUE` ne tourne pas dans un bloc
    transactionnel, et parce qu'une valeur fraichement ajoutee ne peut pas etre
    employee tant que sa transaction n'est pas validee — or les insertions qui
    suivent emploient precisement ces noms.

    SQLite range un enum en VARCHAR : rien a y faire, le dialecte est laisse
    tranquille.
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
    _add_enum_values(op.get_bind(), 'technologytype', NODES)

    # Un noeud a zero pour chaque compte qui en possede deja : les comptes sans
    # technologies sont les non jouables — moderateurs, administrateurs — et
    # n'ont pas a en recevoir.
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
    # On retire les 54 noeuds ajoutes ici et rien d'autre : les 36 d'avant,
    # niveaux compris, restent tels quels.
    removable = [n for n in NODES if n not in PREVIOUS_NODES]
    if removable:
        op.execute(
            "DELETE FROM user_technologies WHERE type IN (%s)"
            % ", ".join("'%s'" % node for node in removable))

    # Une recherche en cours sur un noeud disparu n'a plus d'objet.
    if removable:
        op.execute(
            "DELETE FROM user_event WHERE event_type = 'research' AND (%s)"
            % " OR ".join(
                "_extra_args LIKE '%%\"type\": \"%s\"%%'" % node
                for node in removable))

    # Les valeurs ajoutees aux types enum ne sont pas retirees : Postgres ne
    # sait pas defaire un ADD VALUE, et les laisser en place ne gene rien.
