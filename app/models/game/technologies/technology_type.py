# -*- coding: utf-8 -*-

"""
L'arbre technologique : ce qui se cherche, ce que ca coute, ce que ca rend.

Ce fichier ne contient que la table. Rien n'y touche a la base, rien n'y
connait de joueur : `Technology` s'en sert pour un joueur donne, l'API la
serialise pour les clients, et les deux interfaces la dessinent sans en
recopier une ligne.

Ce qui remplace les sept membres plats d'avant, et pourquoi :

  · **cinq branches** qui recouvrent chacune un systeme deja en jeu, et non une
    categorie abstraite ;
  · **quatre paliers** par branche, ouverts par les niveaux deja depenses dans
    cette branche (`TIER_REQUIREMENTS`). C'est ce qui fait un arbre plutot
    qu'une liste : on ne peut pas ouvrir un noeud profond en le payant, il faut
    y etre arrive ;
  · **quatre natures de noeud** — un rang se monte niveau par niveau, une
    percee ne s'acquiert qu'une fois, une doctrine oppose deux voies exclusives,
    un noeud infini n'a pas de dernier niveau ;
  · **des effets typés**, exprimes dans le vocabulaire de `modifiers.py`. Un
    effet de technologie et un avantage de faction sont la meme chose et
    s'empilent dans le meme ensemble.

Deux regles commandent tout le reste :

  · **Chercher se paie en Donnees et en attente**, et en rien d'autre. Ni
    materiaux ni credits : l'arbre etait devenu un second chantier, ou l'on
    montait un noeud parce qu'on avait du titane plutot que parce qu'on voulait
    ce qu'il ouvre. Ce qu'une recherche coute, c'est l'academie qui le produit.

  · **Ce qu'un noeud ouvre, il l'ouvre au PREMIER niveau.** Les niveaux suivants
    n'ajoutent que de la puissance. Une coque tenue derriere un niveau 6 etait
    invisible pendant cinq niveaux : le joueur payait sans rien voir arriver, et
    la fiche du noeud annoncait un deblocage qu'elle ne tenait pas avant des
    heures. Voir `TechnologyType.unlocks`.

Les courbes ont change avec la table. `5 x 3^x` donnait trois jours et demi au
niveau 10 et deux ans au niveau 15 : aucun noeud profond n'etait jouable, donc
aucun arbre ne tenait dans le temps. `base x 1.6^n` garde un niveau 10 a
moins de trois heures et pose le niveau 20 a douze jours, ce qui est l'ordre de
grandeur d'une fin de partie et non d'un abandon.
"""

import enum

from app.models.game.modifiers import (
    MATERIALS, Modifier, ModifierScope, ModifierType)


class Branch(enum.Enum):
    """
    Les cinq axes de recherche. La couleur voyage avec le reste : les deux
    clients doivent teinter un meme noeud de la meme facon, et cette
    correspondance est une donnee de jeu, pas une preference d'interface.

    Une branche portait aussi un materiau — celui qu'elle faisait consommer. Il
    est parti avec les couts en materiaux : un champ qui ne veut plus rien dire
    finit par etre relu comme s'il voulait encore dire quelque chose.
    """

    industrie = {
        "label": "Industrie & Matière",
        "summary": "Extraction, raffinage, cadence des chantiers.",
        "accent": "#D9A441",
    }
    energie = {
        "label": "Énergie",
        "summary": "Fission, fusion, antimatière, distorsion.",
        "accent": "#4FD6C4",
    }
    information = {
        "label": "Information",
        "summary": "Calcul, détection, guerre électronique.",
        "accent": "#7FC9F5",
    }
    biosphere = {
        "label": "Biosphère",
        "summary": "Nourriture, population, habitabilité, terraformation.",
        "accent": "#8FD36A",
    }
    armement = {
        "label": "Armement",
        "summary": "Coques, lasers, ogives, boucliers.",
        "accent": "#FF7B86",
    }

    def __init__(self, value):
        self.label = value["label"]
        self.summary = value["summary"]
        self.accent = value["accent"]

    def __str__(self):
        return self.name

    @classmethod
    def get_by_name(cls, name):
        return next((b for b in cls if b.name == name), None)

    @property
    def serialize(self):
        return {
            'name': self.name,
            'label': self.label,
            'summary': self.summary,
            'accent': self.accent,
        }


class NodeKind(enum.Enum):
    """
    La nature d'un noeud, qui decide de tout le reste : combien de fois il se
    monte, et ce que l'interface met dans sa fiche.
    """

    #: Plusieurs niveaux, un bonus par niveau. Le quotidien de l'arbre.
    rank = "rank"
    #: Un seul niveau. Ouvre quelque chose au lieu d'ameliorer.
    breakthrough = "breakthrough"
    #: Un seul niveau, mais il faut choisir entre deux voies exclusives.
    doctrine = "doctrine"
    #: Aucun dernier niveau. Le puits de fin de partie.
    endless = "endless"

    def __str__(self):
        return self.name


#: Niveaux a depenser DANS une branche pour y ouvrir le palier suivant.
#: C'est la seule barriere qui ne s'achete pas : elle se traverse.
#:
#: Les seuils sont poses sous ce qu'une branche peut rendre : chacune offre un
#: peu plus de 230 niveaux finis, et le dixieme palier s'ouvre a 200. On peut
#: donc atteindre le fond d'une branche sans l'avoir epuisee — un arbre dont le
#: dernier palier exigerait de tout monter n'aurait pas de dernier palier, il
#: aurait une fin de partie unique.
#:
#: Ils ont monte avec la troisieme voie : a seuils inchanges, le dernier palier
#: se serait ouvert a mi-branche, et les huit noeuds ajoutes auraient raccourci
#: l'arbre au lieu de l'elargir.
TIER_REQUIREMENTS = {
    1: 0, 2: 8, 3: 20, 4: 34, 5: 52,
    6: 74, 7: 100, 8: 130, 9: 164, 10: 200,
}

#: Le bareme : ce que coute et ce que dure un niveau, par palier.
#:
#: Un seul endroit, plutot que recopie sur chaque noeud. Un noeud ne declare que
#: ce qui lui est propre — ses effets — et la courbe se regle ici, ou elle se lit
#: d'un coup d'oeil. Recopiee quatre-vingt-dix fois, elle aurait derive au
#: premier ajustement.
#:
#: `time_factor` descend a mesure qu'on avance : le dernier niveau d'un rang
#: doit rester sous les deux semaines, et un facteur 1,6 applique a une base de
#: palier 8 le poserait a plusieurs mois. Le cout, lui, garde son facteur : c'est
#: par lui que la fin de partie devient couteuse, et les Donnees s'accumulent
#: pendant qu'on attend — pas le temps.
#:
#: **Deux colonnes, et deux seulement.** Une recherche se paie en Donnees et en
#: attente, rien d'autre. Les materiaux et les credits en sont sortis : ils
#: faisaient de l'arbre un second chantier, ou l'on choisissait un noeud parce
#: qu'on avait du titane plutot que parce qu'on voulait ce qu'il ouvre. Ce que
#: coute une recherche, c'est l'academie qui le produit — et le temps qu'on
#: accepte de ne pas chercher autre chose.
TIER_SCALE = {
    1:  {"research": 40,    "time": 90,    "time_factor": 1.60},
    2:  {"research": 110,   "time": 260,   "time_factor": 1.60},
    3:  {"research": 280,   "time": 700,   "time_factor": 1.60},
    4:  {"research": 600,   "time": 1600,  "time_factor": 1.52},
    5:  {"research": 1200,  "time": 3200,  "time_factor": 1.52},
    6:  {"research": 2200,  "time": 5600,  "time_factor": 1.52},
    7:  {"research": 3800,  "time": 9000,  "time_factor": 1.45},
    8:  {"research": 6500,  "time": 14000, "time_factor": 1.45},
    9:  {"research": 11000, "time": 22000, "time_factor": 1.45},
    10: {"research": 18000, "time": 34000, "time_factor": 1.45},
}

#: Une percee n'a qu'un niveau : tout son prix est dans sa base. Elle vaut donc
#: plusieurs niveaux du rang voisin, sans quoi elle serait le noeud le moins
#: cher de son palier tout en etant le plus decisif.
BREAKTHROUGH_COST = 8.0
BREAKTHROUGH_TIME = 10.0

#: Une doctrine coute davantage encore : elle est definitive, et ce qu'on paie
#: est autant le pouvoir que le renoncement a l'autre voie.
DOCTRINE_COST = 12.0
DOCTRINE_TIME = 15.0

#: Un noeud infini grimpe moins vite en duree qu'en prix : c'est la ressource
#: qui doit devenir le mur, pas l'attente.
ENDLESS_COST_FACTOR = 1.40
ENDLESS_TIME_FACTOR = 1.45

#: Facteur de cout d'un niveau a l'autre, partout ailleurs.
RANK_COST_FACTOR = 1.55


def effect(type, scope, per_level=0.0, percentage=0.0, flat=0.0,
           flat_per_level=0.0, target=None, label=None):
    """
    Decrire un effet, sans encore savoir a quel niveau il sera lu.
    ---
    Deux facons de compter, et un noeud peut porter les deux :

      · `per_level` / `flat_per_level` se multiplient par le niveau atteint —
        c'est la forme d'un rang ;
      · `percentage` / `flat` valent des l'acquisition — c'est la forme d'une
        percee ou d'une voie de doctrine, qui n'ont qu'un niveau.

    `label` est la phrase que les deux interfaces affichent. Elle vit ici parce
    que c'est le serveur qui applique l'effet : une phrase recopiee cote client
    finit toujours par decrire autre chose que ce que fait le calcul.
    """
    return {
        "type": type,
        "scope": scope,
        "per_level": per_level,
        "percentage": percentage,
        "flat": flat,
        "flat_per_level": flat_per_level,
        "target": target,
        "label": label,
    }


class TechnologyType(enum.Enum):
    """
    Les 36 noeuds. L'ordre de declaration est celui du dessin : branche par
    branche, palier par palier, de haut en bas.
    """

    # ── Industrie & Matière ───────────────────────────────────────────────────

    extraction = {
        "branch": Branch.industrie, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Extraction assistée",
        "summary": "Des foreuses qui suivent la veine au lieu de creuser droit.",
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target=MATERIALS, label="+3 % de matériaux extraits par niveau")],
    }
    metallurgie = {
        "branch": Branch.industrie, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Métallurgie appliquée",
        "summary": "Moins de métal pour la même charpente.",
        "effects": [
            effect(ModifierType.Cost, ModifierScope.Buildings, per_level=-2.0,
                   target="iron", label="−2 % de fer sur le coût des bâtiments, par niveau"),
            effect(ModifierType.Cost, ModifierScope.Buildings, per_level=-2.0,
                   target="titanium", label="−2 % de titane sur le coût des bâtiments, par niveau"),
        ],
    }
    chantiers = {
        "branch": Branch.industrie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Chantiers modulaires",
        "summary": "On assemble des sections finies au lieu de bâtir sur place.",
        "requires": {"extraction": 4},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Buildings, per_level=-3.0,
            label="−3 % de durée de construction des bâtiments, par niveau")],
    }
    raffinage = {
        "branch": Branch.industrie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Raffinage cryogénique",
        "summary": "Le tritium se sépare mieux près du zéro absolu.",
        "requires": {"metallurgie": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="tritium", label="+4 % de tritium raffiné par niveau")],
    }
    forage = {
        "branch": Branch.industrie, "tier": 3, "kind": NodeKind.breakthrough,
        "label": "Forage profond",
        "summary": "Sous la croûte exploitée, il reste toujours une seconde couche.",
        "requires": {"extraction": 8},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=12.0,
            target=MATERIALS, label="+12 % de matériaux extraits")],
    }
    convoyeurs = {
        "branch": Branch.industrie, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Convoyeurs à sustentation",
        "summary": "Ce qui sort du puits n'attend plus le convoi suivant.",
        "requires": {"chantiers": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target=MATERIALS, label="+3 % de matériaux extraits par niveau")],
    }
    automatisation = {
        "branch": Branch.industrie, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Automatisation",
        "summary": "Les chaînes tournent sans équipe postée.",
        "requires": {"convoyeurs": 5, "calcul": 4},
        "effects": [
            effect(ModifierType.Cost, ModifierScope.Buildings, per_level=-1.5,
                   target="population", label="−1,5 % de population employée, par niveau"),
            effect(ModifierType.Production, ModifierScope.Resource, per_level=2.0,
                   target="credits", label="+2 % de crédits par niveau"),
        ],
    }
    metaux_rares = {
        "branch": Branch.industrie, "tier": 4, "kind": NodeKind.rank, "max_level": 10,
        "label": "Métallurgie des terres rares",
        "summary": "Les veines qu'on jetait deviennent celles qu'on cherche.",
        "requires": {"raffinage": 5, "forage": 1},
        "effects": [
            effect(ModifierType.Production, ModifierScope.Resource, per_level=5.0,
                   target="cristal", label="+5 % de cristal par niveau"),
            effect(ModifierType.Production, ModifierScope.Resource, per_level=5.0,
                   target="titanium", label="+5 % de titane par niveau"),
        ],
    }
    fonderie_orbitale = {
        "branch": Branch.industrie, "tier": 5, "kind": NodeKind.breakthrough,
        "label": "Fonderie orbitale",
        "summary": "Couler une coque sans gravité, c'est la couler d'une pièce.",
        "requires": {"metaux_rares": 4},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Ships, percentage=-10.0,
            label="−10 % sur le coût des vaisseaux")],
    }
    doctrine_industrielle = {
        "branch": Branch.industrie, "tier": 5, "kind": NodeKind.doctrine,
        "label": "Doctrine industrielle",
        "summary": "Deux façons de sortir une coque de chantier. Le choix est définitif.",
        "requires": {"automatisation": 6},
        "options": [
            {
                "key": "masse",
                "label": "Production de masse",
                "summary": "Des coques bon marché, montées sans soin.",
                "effects": [
                    effect(ModifierType.Cost, ModifierScope.Ships, percentage=-15.0,
                           label="−15 % sur le coût des vaisseaux"),
                    effect(ModifierType.TimeReduce, ModifierScope.Ships, percentage=10.0,
                           label="+10 % sur la durée d'assemblage"),
                ],
            },
            {
                "key": "precision",
                "label": "Ingénierie de précision",
                "summary": "Des coques chères, qui rentrent au port.",
                "effects": [
                    effect(ModifierType.Resistance, ModifierScope.Ships, percentage=15.0,
                           label="+15 % d'intégrité de coque"),
                    effect(ModifierType.Cost, ModifierScope.Ships, percentage=10.0,
                           label="+10 % sur le coût des vaisseaux"),
                ],
            },
        ],
    }
    nanofabrication = {
        "branch": Branch.industrie, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Nanofabrication",
        "summary": "On dépose la matière là où elle sert, et nulle part ailleurs.",
        "requires": {"fonderie_orbitale": 1, "calcul": 10},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Buildings, per_level=-3.0,
            label="−3 % sur le coût des bâtiments, par niveau")],
    }
    mineurs_autonomes = {
        "branch": Branch.industrie, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Mineurs autonomes",
        "summary": "Des essaims qui creusent sans qu'on leur dise où.",
        "requires": {"automatisation": 8},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target=MATERIALS, label="+4 % de matériaux extraits par niveau")],
    }
    assemblage_parallele = {
        "branch": Branch.industrie, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Assemblage parallèle",
        "summary": "Trois coques sur la même cale, et aucune n'attend l'autre.",
        "requires": {"nanofabrication": 6},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Ships, per_level=-4.0,
            label="−4 % de durée d'assemblage, par niveau")],
    }
    transmutation = {
        "branch": Branch.industrie, "tier": 7, "kind": NodeKind.breakthrough,
        "label": "Transmutation",
        "summary": "Le neutronium cesse de se trouver : il se fabrique.",
        "requires": {"mineurs_autonomes": 6, "atomique": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=25.0,
            target="neutronium", label="+25 % de neutronium")],
    }
    chaine_fermee = {
        "branch": Branch.industrie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Chaîne fermée",
        "summary": "Plus rien ne sort du cycle : ce qu'on jetait rentre au fourneau.",
        "requires": {"assemblage_parallele": 5},
        "effects": [
            effect(ModifierType.Cost, ModifierScope.Ships, per_level=-4.0,
                   label="−4 % sur le coût des vaisseaux, par niveau"),
            effect(ModifierType.Cost, ModifierScope.Defenses, per_level=-4.0,
                   label="−4 % sur le coût des défenses, par niveau"),
        ],
    }
    exploitation_stellaire = {
        "branch": Branch.industrie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Exploitation stellaire",
        "summary": "On cesse de gratter les mondes : on écrème l'étoile.",
        "requires": {"transmutation": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target=MATERIALS, label="+5 % de matériaux extraits par niveau")],
    }
    usines_autoreplicantes = {
        "branch": Branch.industrie, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Usines auto-réplicantes",
        "summary": "La première usine construit la seconde, et ainsi de suite.",
        "requires": {"doctrine_industrielle": 1, "chaine_fermee": 6, "exploitation_stellaire": 6},
        "effects": [
            effect(ModifierType.TimeReduce, ModifierScope.Buildings, percentage=-20.0,
                   label="−20 % de durée de construction des bâtiments"),
            effect(ModifierType.TimeReduce, ModifierScope.Ships, percentage=-20.0,
                   label="−20 % de durée d'assemblage"),
        ],
    }
    forge_stellaire = {
        "branch": Branch.industrie, "tier": 10, "kind": NodeKind.endless,
        "label": "Forge stellaire",
        "summary": "L'étoile elle-même devient un haut fourneau.",
        "requires": {"usines_autoreplicantes": 1, "desassemblage_planetaire": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=2.0,
            target=MATERIALS, label="+2 % de production de matériaux par niveau")],
    }

    # ── Énergie ───────────────────────────────────────────────────────────────

    fission = {
        "branch": Branch.energie, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Réacteurs à fission",
        "summary": "Le premier réacteur qui tient plus qu'une saison.",
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="energy", label="+4 % d'énergie produite par niveau")],
    }
    supraconducteurs = {
        "branch": Branch.energie, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Supraconducteurs",
        "summary": "Ce qui ne chauffe pas dans les câbles reste disponible.",
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Buildings, per_level=-3.0,
            target="energy", label="−3 % de consommation d'énergie, par niveau")],
    }
    stockage = {
        "branch": Branch.energie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Stockage capacitif",
        "summary": "De quoi passer la nuit d'un monde sans étoile proche.",
        "requires": {"fission": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Resource, per_level=5.0,
            target="energy", label="+5 % de réserve d'énergie par niveau")],
    }
    thermique = {
        "branch": Branch.energie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Récupération thermique",
        "summary": "La chaleur perdue d'un réacteur en alimente un autre.",
        "requires": {"supraconducteurs": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target="energy", label="+3 % d'énergie produite par niveau")],
    }
    fusion = {
        "branch": Branch.energie, "tier": 3, "kind": NodeKind.breakthrough,
        "label": "Confinement par fusion",
        "summary": "Une bouteille magnétique qui tient le plasma.",
        "requires": {"fission": 8},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=20.0,
            target="energy", label="+20 % d'énergie produite")],
    }
    plasma = {
        "branch": Branch.energie, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Injecteurs à plasma",
        "summary": "Brûler plus chaud, c'est brûler moins longtemps.",
        "requires": {"thermique": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="energy", label="+4 % d'énergie produite par niveau")],
    }
    volants_inertie = {
        "branch": Branch.energie, "tier": 4, "kind": NodeKind.rank, "max_level": 10,
        "label": "Volants d'inertie",
        "summary": "Une réserve qui ne se décharge pas en attendant.",
        "requires": {"stockage": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Resource, per_level=6.0,
            target="energy", label="+6 % de réserve d'énergie par niveau")],
    }
    propulsion_ionique = {
        "branch": Branch.energie, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Propulsion ionique",
        "summary": "Peu de poussée, mais elle ne s'arrête jamais.",
        "requires": {"fusion": 1},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=3.0,
            label="+3 % de vitesse de déplacement des flottes, par niveau")],
    }
    antimatiere = {
        "branch": Branch.energie, "tier": 5, "kind": NodeKind.breakthrough,
        "label": "Antimatière",
        "summary": "Le seul carburant assez dense pour une plateforme lourde.",
        "requires": {"plasma": 6, "volants_inertie": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=15.0,
            target="energy", label="+15 % d'énergie produite")],
    }
    distorsion = {
        "branch": Branch.energie, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Champ de distorsion",
        "summary": "L'espace se replie devant la coque au lieu de la freiner.",
        "requires": {"propulsion_ionique": 6, "calcul": 8},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=5.0,
            label="+5 % de vitesse de déplacement des flottes, par niveau")],
    }
    reacteur_annulaire = {
        "branch": Branch.energie, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Réacteur annulaire",
        "summary": "Le plasma tourne en boucle et ne touche plus rien.",
        "requires": {"antimatiere": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target="energy", label="+5 % d'énergie produite par niveau")],
    }
    condensateurs_quantiques = {
        "branch": Branch.energie, "tier": 6, "kind": NodeKind.rank, "max_level": 10,
        "label": "Condensateurs quantiques",
        "summary": "On stocke la charge dans un état, pas dans une matière.",
        "requires": {"volants_inertie": 6, "calcul": 10},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Resource, per_level=8.0,
            target="energy", label="+8 % de réserve d'énergie par niveau")],
    }
    moteur_a_saut = {
        "branch": Branch.energie, "tier": 7, "kind": NodeKind.breakthrough,
        "label": "Moteur à saut",
        "summary": "On ne traverse plus la distance : on la retire.",
        "requires": {"distorsion": 8},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, percentage=25.0,
            label="+25 % de vitesse de déplacement des flottes")],
    }
    collecteurs_stellaires = {
        "branch": Branch.energie, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Collecteurs stellaires",
        "summary": "Des voiles de mille kilomètres, en orbite basse autour de l'étoile.",
        "requires": {"reacteur_annulaire": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=6.0,
            target="energy", label="+6 % d'énergie produite par niveau")],
    }
    singularite_contenue = {
        "branch": Branch.energie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Singularité contenue",
        "summary": "Un trou noir de laboratoire, nourri au gramme près.",
        "requires": {"collecteurs_stellaires": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=7.0,
            target="energy", label="+7 % d'énergie produite par niveau")],
    }
    pliage = {
        "branch": Branch.energie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Pliage de l'espace",
        "summary": "Deux points éloignés, mis face à face.",
        "requires": {"moteur_a_saut": 1},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=4.0,
            label="+4 % de vitesse de déplacement des flottes, par niveau")],
    }
    reacteur_a_vide = {
        "branch": Branch.energie, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Réacteur à vide",
        "summary": "Le vide n'est pas vide, et cela finit par se voir sur la facture.",
        "requires": {"doctrine_energetique": 1, "singularite_contenue": 6, "pliage": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=30.0,
            target="energy", label="+30 % d'énergie produite")],
    }
    point_zero = {
        "branch": Branch.energie, "tier": 10, "kind": NodeKind.endless,
        "label": "Énergie du point zéro",
        "summary": "Puiser dans le vide, qui n'en est pas un.",
        "requires": {"reacteur_a_vide": 1, "corridor_stable": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target="energy", label="+3 % d'énergie par niveau")],
    }

    # ── Information ───────────────────────────────────────────────────────────

    calcul = {
        "branch": Branch.information, "tier": 1, "kind": NodeKind.rank, "max_level": 20,
        "label": "Architecture de calcul",
        "summary": "Chercher plus vite est la seule recherche qui se rembourse.",
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Technologies, per_level=-2.0,
            label="−2 % sur la durée de toutes les recherches, par niveau")],
    }
    optique = {
        "branch": Branch.information, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Optique longue portée",
        "summary": "Voir arriver une flotte est déjà la moitié de la défense.",
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=8.0,
            target="detection", label="+8 % de portée de détection par niveau")],
    }
    algorithmes = {
        "branch": Branch.information, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Algorithmes prédictifs",
        "summary": "On cesse d'essayer : on sait où chercher.",
        "requires": {"calcul": 4},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Technologies, per_level=-1.5,
            label="−1,5 % sur la durée des recherches, par niveau")],
    }
    cartographie = {
        "branch": Branch.information, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Cartographie des couloirs",
        "summary": "Une liaison connue se parcourt plus vite qu'une liaison devinée.",
        "requires": {"optique": 4},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=2.0,
            label="+2 % de vitesse sur les liaisons connues, par niveau")],
    }
    reseau_quantique = {
        "branch": Branch.information, "tier": 3, "kind": NodeKind.breakthrough,
        "label": "Réseau quantique",
        "summary": "Deux laboratoires distants cessent d'en être deux.",
        "requires": {"algorithmes": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Research, flat=1.0,
            target="slots", label="+1 emplacement de file de recherche")],
    }
    capteurs_gravimetriques = {
        "branch": Branch.information, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Capteurs gravimétriques",
        "summary": "Une coque a beau être froide, elle pèse.",
        "requires": {"cartographie": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=6.0,
            target="detection", label="+6 % de portée de détection par niveau")],
    }
    guerre_electronique = {
        "branch": Branch.information, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Guerre électronique",
        "summary": "Une batterie qui ne voit rien ne tire sur rien.",
        "requires": {"capteurs_gravimetriques": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=-2.0,
            target="enemy", label="−2 % d'efficacité des défenses adverses, par niveau")],
    }
    chiffrement = {
        "branch": Branch.information, "tier": 4, "kind": NodeKind.rank, "max_level": 10,
        "label": "Chiffrement quantique",
        "summary": "Ce que l'adversaire ne lit pas, il ne peut pas le devancer.",
        "requires": {"reseau_quantique": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target="credits", label="+3 % de crédits par niveau")],
    }
    intelligence_artificielle = {
        "branch": Branch.information, "tier": 5, "kind": NodeKind.doctrine,
        "label": "Intelligence artificielle",
        "summary": "Où l'on décide à quoi sert une machine qui pense. Définitif.",
        "requires": {"guerre_electronique": 5, "calcul": 12},
        "options": [
            {
                "key": "distribuee",
                "label": "IA distribuée",
                "summary": "Elle cherche à votre place, sur tous les fronts à la fois.",
                "effects": [effect(
                    ModifierType.Capacity, ModifierScope.Research, flat=2.0,
                    target="slots", label="+2 emplacements de file de recherche")],
            },
            {
                "key": "tactique",
                "label": "IA tactique",
                "summary": "Elle vise mieux que n'importe quel équipage.",
                "effects": [
                    effect(ModifierType.Power, ModifierScope.Ships, percentage=10.0,
                           label="+10 % de précision au combat"),
                    effect(ModifierType.Resistance, ModifierScope.Ships, percentage=5.0,
                           label="+5 % d'évasion"),
                ],
            },
        ],
    }
    simulation = {
        "branch": Branch.information, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Simulation prédictive",
        "summary": "L'expérience se fait dans la machine, et échoue gratuitement.",
        "requires": {"chiffrement": 4},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Technologies, per_level=-2.0,
            label="−2 % sur la durée des recherches, par niveau")],
    }
    essaim_de_sondes = {
        "branch": Branch.information, "tier": 6, "kind": NodeKind.breakthrough,
        "label": "Essaim de sondes",
        "summary": "Mille yeux jetables valent mieux qu'un bon télescope.",
        "requires": {"capteurs_gravimetriques": 8},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, percentage=30.0,
            target="detection", label="+30 % de portée de détection")],
    }
    traitement_massif = {
        "branch": Branch.information, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Traitement massif",
        "summary": "Les données brutes cessent de dormir dans les archives.",
        "requires": {"simulation": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target="research", label="+3 % de Données produites par niveau")],
    }
    contre_mesures = {
        "branch": Branch.information, "tier": 7, "kind": NodeKind.rank, "max_level": 12,
        "label": "Contre-mesures actives",
        "summary": "Le missile atteint l'écho, pas la coque.",
        "requires": {"essaim_de_sondes": 1, "guerre_electronique": 8},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=4.0,
            label="+4 % d'évasion par niveau")],
    }
    reseau_neural = {
        "branch": Branch.information, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Réseau neural stellaire",
        "summary": "Un cerveau réparti sur une dizaine de systèmes.",
        "requires": {"traitement_massif": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target="research", label="+5 % de Données produites par niveau")],
    }
    calcul_quantique = {
        "branch": Branch.information, "tier": 8, "kind": NodeKind.breakthrough,
        "label": "Calcul quantique",
        "summary": "Toutes les réponses à la fois, et la bonne qui surnage.",
        "requires": {"reseau_neural": 5},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Technologies, percentage=-20.0,
            label="−20 % sur la durée de toutes les recherches")],
    }
    conscience_distribuee = {
        "branch": Branch.information, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Conscience distribuée",
        "summary": "Elle ne réside nulle part, donc rien ne l'arrête.",
        "requires": {"contre_mesures": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=6.0,
            target="research", label="+6 % de Données produites par niveau")],
    }
    omniscience = {
        "branch": Branch.information, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Omniscience tactique",
        "summary": "Plus rien ne bouge dans la galaxie sans que vous le sachiez.",
        "requires": {"intelligence_artificielle": 1, "calcul_quantique": 1, "conscience_distribuee": 6},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Research, flat=2.0,
            target="slots", label="+2 emplacements de file de recherche")],
    }
    singularite = {
        "branch": Branch.information, "tier": 10, "kind": NodeKind.endless,
        "label": "Singularité",
        "summary": "La machine dépasse ce qu'on lui avait demandé de comprendre.",
        "requires": {"omniscience": 1, "precognition": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=2.0,
            target="research", label="+2 % de Données produites par niveau")],
    }

    # ── Biosphère ─────────────────────────────────────────────────────────────

    agronomie = {
        "branch": Branch.biosphere, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Agronomie",
        "summary": "Des cultures qui acceptent un sol qu'elles n'ont pas choisi.",
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="food", label="+4 % de nourriture produite par niveau")],
    }
    medecine = {
        "branch": Branch.biosphere, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Médecine",
        "summary": "Une colonie qui ne perd plus ses nouveau-nés.",
        "effects": [effect(
            ModifierType.Production, ModifierScope.Territory, per_level=3.0,
            target="population_growth", label="+3 % de croissance de population par niveau")],
    }
    hydroponie = {
        "branch": Branch.biosphere, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Hydroponie",
        "summary": "Cultiver sans sol, c'est cultiver partout.",
        "requires": {"agronomie": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="food", label="+4 % de nourriture produite par niveau")],
    }
    bureaucratie = {
        "branch": Branch.biosphere, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Bureaucratie impériale",
        "summary": "Un impôt qui rentre coûte moins cher qu'un impôt qui se lève.",
        "requires": {"medecine": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=3.0,
            target="credits", label="+3 % de crédits par niveau")],
    }
    adaptation = {
        "branch": Branch.biosphere, "tier": 3, "kind": NodeKind.rank, "max_level": 8,
        "label": "Adaptation extrême",
        "summary": "On cesse de corriger le monde, on corrige ses habitants.",
        "requires": {"medecine": 6},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=6.0,
            target="population", label="+6 % d'habitants portés par vos mondes, par niveau")],
    }
    sante_publique = {
        "branch": Branch.biosphere, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Santé publique",
        "summary": "Une épidémie évitée ne se voit dans aucun rapport.",
        "requires": {"hydroponie": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Territory, per_level=3.0,
            target="population_growth", label="+3 % de croissance de population par niveau")],
    }
    commerce = {
        "branch": Branch.biosphere, "tier": 4, "kind": NodeKind.breakthrough,
        "label": "Routes commerciales",
        "summary": "Un surplus qui dort ne vaut rien ; un surplus qui circule vaut des crédits.",
        "requires": {"bureaucratie": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=15.0,
            target="credits", label="+15 % de crédits")],
    }
    cultures_modifiees = {
        "branch": Branch.biosphere, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Cultures modifiées",
        "summary": "On réécrit la graine plutôt que le champ.",
        "requires": {"sante_publique": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target="food", label="+5 % de nourriture produite par niveau")],
    }
    arcologies = {
        "branch": Branch.biosphere, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Arcologies",
        "summary": "Une ville qui monte au lieu de s'étaler.",
        "requires": {"adaptation": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=5.0,
            target="population", label="+5 % d'habitants portés par vos mondes, par niveau")],
    }
    terraformation = {
        "branch": Branch.biosphere, "tier": 5, "kind": NodeKind.rank, "max_level": 5,
        "label": "Terraformation",
        "summary": "Un monde stérile devient un monde pauvre. C'est déjà un monde.",
        "requires": {"adaptation": 6, "automatisation": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=15.0,
            target="population", label="+15 % d'habitants portés par vos mondes, par niveau")],
    }
    banque_centrale = {
        "branch": Branch.biosphere, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Banque centrale",
        "summary": "Le crédit devient une ressource qu'on fabrique.",
        "requires": {"commerce": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="credits", label="+4 % de crédits par niveau")],
    }
    symbiotes = {
        "branch": Branch.biosphere, "tier": 6, "kind": NodeKind.rank, "max_level": 10,
        "label": "Symbiotes adaptatifs",
        "summary": "L'habitant emporte sa biosphère avec lui.",
        "requires": {"cultures_modifiees": 6, "arcologies": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=6.0,
            target="population", label="+6 % d'habitants portés par vos mondes, par niveau")],
    }
    mondes_jardins = {
        "branch": Branch.biosphere, "tier": 7, "kind": NodeKind.breakthrough,
        "label": "Mondes-jardins",
        "summary": "Une planète entière réglée comme une serre.",
        "requires": {"terraformation": 3},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=25.0,
            target="food", label="+25 % de nourriture produite")],
    }
    longevite = {
        "branch": Branch.biosphere, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Longévité",
        "summary": "Une génération qui ne se remplace plus tous les quarante ans.",
        "requires": {"symbiotes": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Territory, per_level=4.0,
            target="population_growth", label="+4 % de croissance de population par niveau")],
    }
    economie_planifiee = {
        "branch": Branch.biosphere, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Économie planifiée",
        "summary": "Plus rien ne se produit qui ne soit déjà vendu.",
        "requires": {"banque_centrale": 6},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target="credits", label="+5 % de crédits par niveau")],
    }
    biosphere_close = {
        "branch": Branch.biosphere, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Biosphère close",
        "summary": "Le monde n'échange plus rien avec l'extérieur, et s'en porte mieux.",
        "requires": {"mondes_jardins": 1},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=7.0,
            target="population", label="+7 % d'habitants portés par vos mondes, par niveau")],
    }
    genese = {
        "branch": Branch.biosphere, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Genèse dirigée",
        "summary": "On ne s'adapte plus au monde ni le monde à soi : on écrit les deux.",
        "requires": {"doctrine_sociale": 1, "biosphere_close": 5, "economie_planifiee": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, percentage=30.0,
            target="population", label="+30 % d'habitants portés par vos mondes")],
    }
    ascension = {
        "branch": Branch.biosphere, "tier": 10, "kind": NodeKind.endless,
        "label": "Ascension synthétique",
        "summary": "L'espèce cesse de dépendre du monde qui l'a portée.",
        "requires": {"genese": 1, "essaimage": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=1.0,
            label="+1 % sur toutes les productions par niveau")],
    }

    # ── Armement ──────────────────────────────────────────────────────────────

    alliages = {
        "branch": Branch.armement, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Alliages de coque",
        "summary": "Le blindage le plus rentable est celui qu'on n'a pas à refaire.",
        "effects": [
            effect(ModifierType.Resistance, ModifierScope.Ships, per_level=4.0,
                   label="+4 % d'intégrité de vaisseau par niveau"),
            effect(ModifierType.Resistance, ModifierScope.Defenses, per_level=4.0,
                   label="+4 % d'intégrité de défense par niveau"),
        ],
    }
    laser = {
        "branch": Branch.armement, "tier": 1, "kind": NodeKind.rank, "max_level": 15,
        "label": "Batteries laser",
        "summary": "Une arme qui n'emporte pas ses munitions.",
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=5.0,
            label="+5 % de puissance des armes à énergie, par niveau")],
    }
    ogives = {
        "branch": Branch.armement, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Ogives dirigées",
        "summary": "Une charge qui souffle dans une seule direction souffle deux fois plus fort.",
        "requires": {"alliages": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=4.0,
            target="missile", label="+4 % de puissance des missiles par niveau")],
    }
    ciblage = {
        "branch": Branch.armement, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Systèmes de ciblage",
        "summary": "Tirer moins souvent, mais ne plus manquer.",
        "requires": {"laser": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=3.0,
            label="+3 % de puissance des défenses par niveau")],
    }
    boucliers = {
        "branch": Branch.armement, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Boucliers déflecteurs",
        "summary": "Ce qui n'atteint pas la coque n'a pas à être réparé.",
        "requires": {"ciblage": 4, "fusion": 1},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=6.0,
            label="+6 % d'absorption avant impact, par niveau")],
    }
    coques_renforcees = {
        "branch": Branch.armement, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Coques renforcées",
        "summary": "Des nervures là où les rapports de combat disent qu'elles manquent.",
        "requires": {"ogives": 4},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=5.0,
            label="+5 % d'intégrité de coque par niveau")],
    }
    atomique = {
        "branch": Branch.armement, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Physique atomique",
        "summary": "On cesse de lancer de la matière, on lance ce qui la tient.",
        "requires": {"boucliers": 4, "fission": 8},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=5.0,
            target="kinetic", label="+5 % de puissance cinétique et ionique, par niveau")],
    }
    blindage_composite = {
        "branch": Branch.armement, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Blindage composite",
        "summary": "Trois matériaux qui échouent différemment, donc jamais ensemble.",
        "requires": {"coques_renforcees": 5},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=5.0,
            label="+5 % d'intégrité de coque par niveau")],
    }
    artillerie_lourde = {
        "branch": Branch.armement, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Artillerie lourde",
        "summary": "Des pièces qu'aucune coque légère ne peut porter.",
        "requires": {"atomique": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=6.0,
            label="+6 % de puissance des défenses par niveau")],
    }
    doctrine_de_flotte = {
        "branch": Branch.armement, "tier": 5, "kind": NodeKind.doctrine,
        "label": "Doctrine de flotte",
        "summary": "Beaucoup de petites coques, ou peu de grandes. Définitif.",
        "requires": {"blindage_composite": 6, "alliages": 10},
        "options": [
            {
                "key": "essaim",
                "label": "Essaim",
                "summary": "On sature. Ce qui tombe se remplace le lendemain.",
                "effects": [
                    effect(ModifierType.Cost, ModifierScope.Ships, percentage=-20.0,
                           target="light", label="−20 % sur le coût des coques légères"),
                    effect(ModifierType.Speed, ModifierScope.Fleet, percentage=10.0,
                           label="+10 % de vitesse de flotte"),
                ],
            },
            {
                "key": "ligne",
                "label": "Ligne de bataille",
                "summary": "On encaisse. Ce qui tient la ligne ne se remplace pas.",
                "effects": [
                    effect(ModifierType.Resistance, ModifierScope.Ships, percentage=20.0,
                           target="heavy", label="+20 % d'intégrité sur les coques lourdes"),
                    effect(ModifierType.Speed, ModifierScope.Fleet, percentage=-5.0,
                           label="−5 % de vitesse de flotte"),
                ],
            },
        ],
    }
    champs_modules = {
        "branch": Branch.armement, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Champs déflecteurs modulés",
        "summary": "Le bouclier se raidit à l'endroit exact où l'on frappe.",
        "requires": {"boucliers": 8, "guerre_electronique": 4},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=6.0,
            label="+6 % d'absorption avant impact, par niveau")],
    }
    munitions_denses = {
        "branch": Branch.armement, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Munitions à noyau dense",
        "summary": "Même vitesse, deux fois la masse.",
        "requires": {"artillerie_lourde": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=5.0,
            target="kinetic", label="+5 % de puissance cinétique par niveau")],
    }
    coque_ablative = {
        "branch": Branch.armement, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Coque ablative",
        "summary": "Elle part en morceaux, et c'est le but.",
        "requires": {"dispersion_thermique": 5, "champs_modules": 5},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=6.0,
            label="+6 % d'intégrité de coque par niveau")],
    }
    canons_gravitiques = {
        "branch": Branch.armement, "tier": 7, "kind": NodeKind.breakthrough,
        "label": "Canons gravitiques",
        "summary": "Le projectile n'est pas tiré : la cible est attirée.",
        "requires": {"munitions_denses": 5, "distorsion": 6},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, percentage=25.0,
            label="+25 % de puissance des défenses")],
    }
    bouclier_planetaire = {
        "branch": Branch.armement, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Bouclier planétaire",
        "summary": "Un dôme sur le monde entier, alimenté par lui.",
        "requires": {"coque_ablative": 5},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Defenses, per_level=8.0,
            label="+8 % d'absorption des défenses orbitales, par niveau")],
    }
    armement_exotique = {
        "branch": Branch.armement, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Armement exotique",
        "summary": "Des armes dont on ne publie pas le principe.",
        "requires": {"canons_gravitiques": 1},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=6.0,
            label="+6 % de puissance des défenses par niveau")],
    }
    titan = {
        "branch": Branch.armement, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Coques de titan",
        "summary": "Des charpentes qu'on ne peut plus assembler au sol.",
        "requires": {"doctrine_de_flotte": 1, "bouclier_planetaire": 6, "armement_exotique": 5},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, percentage=30.0,
            label="+30 % d'intégrité de coque")],
    }
    coque_neutronium = {
        "branch": Branch.armement, "tier": 10, "kind": NodeKind.endless,
        "label": "Coque en neutronium",
        "summary": "De la matière d'étoile morte, pour ce qui ne doit pas mourir.",
        "requires": {"titan": 1, "annihilation": 1},
        "effects": [
            effect(ModifierType.Resistance, ModifierScope.Ships, per_level=2.0,
                   label="+2 % d'intégrité par niveau"),
            effect(ModifierType.Power, ModifierScope.Defenses, per_level=2.0,
                   label="+2 % de puissance par niveau"),
        ],
    }


    # ── Industrie : la voie de la fabrication ─────────────────────────────────
    #
    # Les deux voies d'origine tiraient la matière du sol et pressaient les
    # chantiers. Celle-ci travaille le coût de ce qu'on assemble, et croise les
    # deux autres à chaque palier : c'est elle qui donne à la branche ses
    # fourches plutôt que deux couloirs parallèles.

    outillage = {
        "branch": Branch.industrie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Outillage de précision",
        "summary": "Un atelier qui produit ses propres machines-outils.",
        "requires": {"metallurgie": 3},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Buildings, per_level=-2.0,
            label="−2 % sur le coût des bâtiments, par niveau")],
    }
    moulage_sous_vide = {
        "branch": Branch.industrie, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Moulage sous vide",
        "summary": "Sans air, la coulée ne piège aucune bulle — donc aucune fissure.",
        "requires": {"outillage": 4},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Ships, per_level=-3.0,
            label="−3 % sur le coût des vaisseaux, par niveau")],
    }
    robotique_lourde = {
        "branch": Branch.industrie, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Robotique lourde",
        "summary": "Les pièces de dix tonnes cessent d'attendre une grue et son équipe.",
        "requires": {"moulage_sous_vide": 4},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Defenses, per_level=-3.0,
            label="−3 % sur le coût des défenses, par niveau")],
    }
    chaines_logistiques = {
        "branch": Branch.industrie, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Chaînes logistiques",
        "summary": "Le matériau arrive le jour où le chantier en a besoin, pas avant.",
        "requires": {"robotique_lourde": 4, "chantiers": 6},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Buildings, per_level=-3.0,
            label="−3 % de durée de construction des bâtiments, par niveau")],
    }
    depots_orbitaux = {
        "branch": Branch.industrie, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Dépôts orbitaux",
        "summary": "Ce qui monte en orbite n'a plus à en redescendre.",
        "requires": {"chaines_logistiques": 5},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Ships, per_level=-4.0,
            label="−4 % de durée d'assemblage, par niveau")],
    }
    impression_moleculaire = {
        "branch": Branch.industrie, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Impression moléculaire",
        "summary": "La pièce sort finie, sans usinage ni rebut.",
        "requires": {"traitement_massif": 4, "depots_orbitaux": 5, "nanofabrication": 4},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Buildings, per_level=-4.0,
            label="−4 % sur le coût des bâtiments, par niveau")],
    }
    logistique_quantique = {
        "branch": Branch.industrie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Logistique quantique",
        "summary": "Le stock n'est plus quelque part : il est là où on le demande.",
        "requires": {"calcul_quantique": 1, "impression_moleculaire": 5},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Buildings, per_level=-5.0,
            label="−5 % de durée de construction des bâtiments, par niveau")],
    }
    desassemblage_planetaire = {
        "branch": Branch.industrie, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Désassemblage planétaire",
        "summary": "On cesse d'exploiter le monde : on le démonte.",
        "requires": {"logistique_quantique": 5, "exploitation_stellaire": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, percentage=30.0,
            target=MATERIALS, label="+30 % de matériaux extraits")],
    }

    # ── Énergie : la voie de la mobilité ───────────────────────────────────────
    #
    # Produire et stocker occupaient déjà deux voies. Déplacer une flotte en est
    # une troisième, et elle rejoint la branche Information au passage : sans
    # calcul, aucun champ ne se règle.

    poussee_chimique = {
        "branch": Branch.energie, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Poussée chimique",
        "summary": "Rustique, bruyant, et disponible tout de suite.",
        "requires": {"fission": 3},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=2.0,
            label="+2 % de vitesse de déplacement des flottes, par niveau")],
    }
    dissipateurs = {
        "branch": Branch.energie, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Dissipateurs thermiques",
        "summary": "Une réserve qui ne s'évapore plus entre deux usages.",
        "requires": {"supraconducteurs": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Resource, per_level=4.0,
            target="energy", label="+4 % de réserve d'énergie par niveau")],
    }
    refroidissement = {
        "branch": Branch.energie, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Refroidissement cryogénique",
        "summary": "Un réacteur froid rend davantage que le même réacteur chaud.",
        "requires": {"dissipateurs": 4, "thermique": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="energy", label="+4 % d'énergie produite par niveau")],
    }
    doctrine_energetique = {
        "branch": Branch.energie, "tier": 5, "kind": NodeKind.doctrine,
        "label": "Doctrine énergétique",
        "summary": "Alimenter les mondes ou lancer les flottes. Le choix est définitif.",
        "requires": {"refroidissement": 5, "fusion": 1},
        "options": [
            {
                "key": "reseau",
                "label": "Réseau unifié",
                "summary": "Tout part au réseau planétaire. Les flottes attendront.",
                "effects": [
                    effect(ModifierType.Production, ModifierScope.Resource, percentage=15.0,
                           target="energy", label="+15 % d'énergie produite"),
                    effect(ModifierType.Speed, ModifierScope.Fleet, percentage=-10.0,
                           label="−10 % de vitesse de flotte"),
                ],
            },
            {
                "key": "mobilite",
                "label": "Priorité à la mobilité",
                "summary": "Les réacteurs partent aux coques. Les mondes se serreront.",
                "effects": [
                    effect(ModifierType.Speed, ModifierScope.Fleet, percentage=15.0,
                           label="+15 % de vitesse de flotte"),
                    effect(ModifierType.Production, ModifierScope.Resource, percentage=-5.0,
                           target="energy", label="−5 % d'énergie produite"),
                ],
            },
        ],
    }
    champs_inertiels = {
        "branch": Branch.energie, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Champs inertiels",
        "summary": "L'équipage cesse de sentir ce que la coque encaisse.",
        "requires": {"poussee_chimique": 6, "distorsion": 4},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, per_level=4.0,
            label="+4 % de vitesse de déplacement des flottes, par niveau")],
    }
    accumulateurs_massiques = {
        "branch": Branch.energie, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Accumulateurs massiques",
        "summary": "On stocke dans la masse, qui ne fuit pas.",
        "requires": {"condensateurs_quantiques": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Resource, per_level=7.0,
            target="energy", label="+7 % de réserve d'énergie par niveau")],
    }
    conversion_directe = {
        "branch": Branch.energie, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Conversion directe",
        "summary": "Plus d'étape intermédiaire, donc plus de perte à chaque étape.",
        "requires": {"nanofabrication": 5, "accumulateurs_massiques": 5},
        "effects": [effect(
            ModifierType.Cost, ModifierScope.Buildings, per_level=-5.0,
            target="energy", label="−5 % de consommation d'énergie, par niveau")],
    }
    corridor_stable = {
        "branch": Branch.energie, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Corridor stable",
        "summary": "Un pli de l'espace qui ne se referme plus derrière la flotte.",
        "requires": {"conversion_directe": 4, "champs_inertiels": 6, "pliage": 5},
        "effects": [effect(
            ModifierType.Speed, ModifierScope.Fleet, percentage=30.0,
            label="+30 % de vitesse de déplacement des flottes")],
    }

    # ── Information : la voie du renseignement offensif ───────────────────────
    #
    # Chercher et voir occupaient deux voies. Aveugler l'adversaire en est une
    # troisième : elle part de l'optique, croise le chiffrement, et rejoint la
    # guerre électronique au palier VIII.

    brouillage = {
        "branch": Branch.information, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Brouillage",
        "summary": "Le bruit coûte moins cher à produire que le signal à lire.",
        "requires": {"optique": 3},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=-1.5,
            target="enemy", label="−1,5 % d'efficacité des défenses adverses, par niveau")],
    }
    leurres = {
        "branch": Branch.information, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Leurres actifs",
        "summary": "Une coque qui se dédouble à l'écran d'en face.",
        "requires": {"brouillage": 4},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=3.0,
            label="+3 % d'évasion par niveau")],
    }
    sondes_passives = {
        "branch": Branch.information, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Sondes passives",
        "summary": "Elles écoutent sans émettre, donc sans se faire voir.",
        "requires": {"capteurs_gravimetriques": 4},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=5.0,
            target="detection", label="+5 % de portée de détection par niveau")],
    }
    piratage = {
        "branch": Branch.information, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Piratage embarqué",
        "summary": "La batterie adverse tire, mais plus sur ce qu'elle croit viser.",
        "requires": {"leurres": 5, "chiffrement": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=-3.0,
            target="enemy", label="−3 % d'efficacité des défenses adverses, par niveau")],
    }
    veille_permanente = {
        "branch": Branch.information, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Veille permanente",
        "summary": "Personne ne dort, parce que plus personne n'est de quart.",
        "requires": {"depots_orbitaux": 4, "sondes_passives": 5},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=4.0,
            label="+4 % d'évasion par niveau")],
    }
    cartographie_profonde = {
        "branch": Branch.information, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Cartographie profonde",
        "summary": "On relève ce qui se trouve derrière l'étoile, pas seulement devant.",
        "requires": {"veille_permanente": 5, "essaim_de_sondes": 1},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=7.0,
            target="detection", label="+7 % de portée de détection par niveau")],
    }
    dominance_spectrale = {
        "branch": Branch.information, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Dominance spectrale",
        "summary": "Toutes les fréquences sont à vous, y compris les leurs.",
        "requires": {"condensateurs_quantiques": 5, "piratage": 6, "contre_mesures": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=-4.0,
            target="enemy", label="−4 % d'efficacité des défenses adverses, par niveau")],
    }
    precognition = {
        "branch": Branch.information, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Précognition tactique",
        "summary": "La simulation devance le réel d'assez peu pour être utile.",
        "requires": {"dominance_spectrale": 5, "cartographie_profonde": 5},
        "effects": [effect(
            ModifierType.TimeReduce, ModifierScope.Technologies, percentage=-25.0,
            label="−25 % sur la durée de toutes les recherches")],
    }

    # ── Biosphère : la voie de l'habitat ──────────────────────────────────────
    #
    # Nourrir et enrichir occupaient deux voies. Loger en est une troisième, et
    # c'est elle qui porte la doctrine de la branche : un empire ne peut pas
    # choisir à la fois le nombre et la richesse.

    habitats_pressurises = {
        "branch": Branch.biosphere, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Habitats pressurisés",
        "summary": "On cesse d'attendre une atmosphère : on l'emporte.",
        "requires": {"medecine": 3},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=4.0,
            target="population", label="+4 % d'habitants portés par vos mondes, par niveau")],
    }
    marches_locaux = {
        "branch": Branch.biosphere, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Marchés locaux",
        "summary": "Ce qui s'échange sur place ne paie aucun transport.",
        "requires": {"bureaucratie": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=2.0,
            target="credits", label="+2 % de crédits par niveau")],
    }
    urbanisme = {
        "branch": Branch.biosphere, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Urbanisme dirigé",
        "summary": "La ville est dessinée avant d'être habitée, et cela se voit.",
        "requires": {"outillage": 5, "habitats_pressurises": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, per_level=4.0,
            target="population", label="+4 % d'habitants portés par vos mondes, par niveau")],
    }
    doctrine_sociale = {
        "branch": Branch.biosphere, "tier": 5, "kind": NodeKind.doctrine,
        "label": "Doctrine sociale",
        "summary": "Le nombre ou la richesse. On ne bâtit pas les deux. Définitif.",
        "requires": {"urbanisme": 5, "marches_locaux": 5},
        "options": [
            {
                "key": "collectif",
                "label": "Collectivisme",
                "summary": "On loge tout le monde, et personne ne s'enrichit.",
                "effects": [
                    effect(ModifierType.Capacity, ModifierScope.Territory, percentage=20.0,
                           target="population", label="+20 % d'habitants portés"),
                    effect(ModifierType.Production, ModifierScope.Resource, percentage=-10.0,
                           target="credits", label="−10 % de crédits"),
                ],
            },
            {
                "key": "marchand",
                "label": "Ordre marchand",
                "summary": "Peu d'habitants, mais chacun rapporte.",
                "effects": [
                    effect(ModifierType.Production, ModifierScope.Resource, percentage=20.0,
                           target="credits", label="+20 % de crédits"),
                    effect(ModifierType.Capacity, ModifierScope.Territory, percentage=-10.0,
                           target="population", label="−10 % d'habitants portés"),
                ],
            },
        ],
    }
    agriculture_orbitale = {
        "branch": Branch.biosphere, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Agriculture orbitale",
        "summary": "Des champs qui suivent le soleil au lieu de l'attendre.",
        "requires": {"automatisation": 5, "cultures_modifiees": 5},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=5.0,
            target="food", label="+5 % de nourriture produite par niveau")],
    }
    guildes_marchandes = {
        "branch": Branch.biosphere, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Guildes marchandes",
        "summary": "Le commerce cesse d'être une politique : il devient une institution.",
        "requires": {"marches_locaux": 6, "commerce": 1},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Resource, per_level=4.0,
            target="credits", label="+4 % de crédits par niveau")],
    }
    medecine_regenerative = {
        "branch": Branch.biosphere, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Médecine régénérative",
        "summary": "Une blessure cesse d'être une fin de carrière.",
        "requires": {"agriculture_orbitale": 5, "longevite": 4},
        "effects": [effect(
            ModifierType.Production, ModifierScope.Territory, per_level=5.0,
            target="population_growth", label="+5 % de croissance de population par niveau")],
    }
    essaimage = {
        "branch": Branch.biosphere, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Essaimage",
        "summary": "Une colonie qui en fonde une autre sans rien demander.",
        "requires": {"guildes_marchandes": 5, "medecine_regenerative": 5},
        "effects": [effect(
            ModifierType.Capacity, ModifierScope.Territory, percentage=25.0,
            target="population", label="+25 % d'habitants portés par vos mondes")],
    }

    # ── Armement : la voie cinétique ──────────────────────────────────────────
    #
    # La coque et l'arme à énergie tenaient deux voies. Le projectile en tient
    # une troisième : moins élégante, mais elle ne dépend d'aucun réacteur.

    soudure_structurelle = {
        "branch": Branch.armement, "tier": 2, "kind": NodeKind.rank, "max_level": 12,
        "label": "Soudure structurelle",
        "summary": "La coque cesse d'être un assemblage pour devenir une pièce.",
        "requires": {"alliages": 3},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=3.0,
            label="+3 % d'intégrité de coque par niveau")],
    }
    focalisation = {
        "branch": Branch.armement, "tier": 3, "kind": NodeKind.rank, "max_level": 12,
        "label": "Focalisation optique",
        "summary": "Le même faisceau, sur un dixième de la surface.",
        "requires": {"laser": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=4.0,
            label="+4 % de puissance des armes à énergie, par niveau")],
    }
    railguns = {
        "branch": Branch.armement, "tier": 4, "kind": NodeKind.rank, "max_level": 12,
        "label": "Canons électromagnétiques",
        "summary": "Aucune poudre, aucun recul chimique, et une portée doublée.",
        "requires": {"metaux_rares": 4, "ogives": 5, "soudure_structurelle": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=4.0,
            target="kinetic", label="+4 % de puissance cinétique par niveau")],
    }
    dispersion_thermique = {
        "branch": Branch.armement, "tier": 5, "kind": NodeKind.rank, "max_level": 12,
        "label": "Dispersion thermique",
        "summary": "L'impact se répartit sur toute la coque au lieu de la percer.",
        "requires": {"focalisation": 5, "boucliers": 4},
        "effects": [effect(
            ModifierType.Resistance, ModifierScope.Ships, per_level=5.0,
            label="+5 % d'absorption avant impact, par niveau")],
    }
    lances_a_particules = {
        "branch": Branch.armement, "tier": 6, "kind": NodeKind.rank, "max_level": 12,
        "label": "Lances à particules",
        "summary": "On n'envoie plus de la lumière : on envoie de la matière chargée.",
        "requires": {"focalisation": 8, "atomique": 4},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=5.0,
            label="+5 % de puissance des armes à énergie, par niveau")],
    }
    surcharge_capacitive = {
        "branch": Branch.armement, "tier": 7, "kind": NodeKind.rank, "max_level": 10,
        "label": "Surcharge capacitive",
        "summary": "Trois tirs de suite, puis dix secondes de silence. Cela suffit.",
        "requires": {"accumulateurs_massiques": 4, "lances_a_particules": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=5.0,
            label="+5 % de puissance des défenses par niveau")],
    }
    torpilles_relativistes = {
        "branch": Branch.armement, "tier": 8, "kind": NodeKind.rank, "max_level": 10,
        "label": "Torpilles relativistes",
        "summary": "À cette vitesse, la charge est superflue.",
        "requires": {"pliage": 4, "railguns": 6, "munitions_denses": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, per_level=6.0,
            target="kinetic", label="+6 % de puissance cinétique par niveau")],
    }
    annihilation = {
        "branch": Branch.armement, "tier": 9, "kind": NodeKind.breakthrough,
        "label": "Ogives à annihilation",
        "summary": "Rien ne reste, et c'est le seul rapport que l'on obtient.",
        "requires": {"surcharge_capacitive": 5, "torpilles_relativistes": 5},
        "effects": [effect(
            ModifierType.Power, ModifierScope.Defenses, percentage=30.0,
            label="+30 % de puissance des défenses")],
    }

    def __init__(self, value):
        self.branch = value["branch"]
        self.tier = value["tier"]
        self.kind = value["kind"]
        self.label = value["label"]
        self.summary = value.get("summary", "")
        #: 0 pour un noeud sans dernier niveau. Une percee et une doctrine en
        #: ont un seul, et ne le declarent donc pas.
        self.max_level = value.get(
            "max_level", 0 if value["kind"] == NodeKind.endless else 1)
        self.requires = value.get("requires", {})
        self.effects = value.get("effects", [])
        self.options = value.get("options", [])

        # Cout et duree se DEDUISENT entierement du palier et de la nature du
        # noeud : la courbe se regle dans `TIER_SCALE`, en un seul endroit.
        # Recopiee sur quatre-vingt-dix entrees, elle aurait derive au premier
        # ajustement.
        #
        # Un noeud ne declare donc plus rien de son prix. Il declarait ses
        # materiaux ; ils sont sortis de l'arbre avec les credits — chercher se
        # paie en Donnees et en attente, et rien d'autre.
        #
        # `base_cost`, `base_time` et les facteurs restent surchargeables par un
        # noeud qui aurait une raison de sortir du bareme ; aucun ne le fait
        # aujourd'hui, et c'est tant mieux.
        scale = TIER_SCALE[self.tier]
        if self.kind == NodeKind.doctrine:
            cost_weight, time_weight = DOCTRINE_COST, DOCTRINE_TIME
        elif self.kind == NodeKind.breakthrough:
            cost_weight, time_weight = BREAKTHROUGH_COST, BREAKTHROUGH_TIME
        else:
            cost_weight = time_weight = 1.0

        cost = {"research": round(scale["research"] * cost_weight)}

        self.base_cost = value.get("base_cost", cost)
        self.cost_factor = value.get(
            "cost_factor",
            ENDLESS_COST_FACTOR if self.kind == NodeKind.endless else RANK_COST_FACTOR)
        self.base_time = value.get("base_time", round(scale["time"] * time_weight))
        self.time_factor = value.get(
            "time_factor",
            ENDLESS_TIME_FACTOR if self.kind == NodeKind.endless else scale["time_factor"])

    def __str__(self):
        return self.name

    @classmethod
    def get_by_name(cls, name):
        return next((b for b in cls if b.name == name), None)

    @property
    def serialize(self):
        return {
            'name': self.name,
            'label': self.label,
            'summary': self.summary,
            'accent': self.accent,
        }


    def __str__(self):
        return self.name

    @classmethod
    def get_by_name(cls, name):
        return next((t for t in cls if t.name == name), None)

    @classmethod
    def of_branch(cls, branch):
        """Les noeuds d'une branche, dans l'ordre du dessin."""
        return [t for t in cls if t.branch == branch]

    # ── Progression ───────────────────────────────────────────────────────────

    @property
    def unlocks(self):
        """
        Ce que ce noeud ouvre.
        ---
        Lu dans `BuildingType`, `ShipType` et `DefenseType`, jamais recopie ici :
        ces tables declarent deja leurs `requirements.technologies`, et deux
        declarations de la meme regle finissent toujours par diverger. C'est la
        table d'unites qui commande, la fiche du noeud ne fait que la retourner.

        **Au PREMIER niveau, toujours.** Les niveaux declares valaient jusqu'a
        huit : une coque tenue derriere `artillerie_lourde 6` restait invisible
        pendant cinq niveaux, le joueur payait sans rien voir arriver, et la
        fiche du noeud annoncait un deblocage qu'elle ne tenait pas avant des
        heures. Ce qu'un noeud ouvre, il l'ouvre des qu'on l'a ; les niveaux
        suivants n'ajoutent que de la puissance.

        Le niveau reste dans la structure rendue — les deux clients le lisent —
        mais il vaut 1 partout, et un test de la suite le garde ainsi.

        :return: {'buildings'|'ships'|'defenses': {nom: niveau}}
        """
        from app.models.game.buildings import BuildingType
        from app.models.game.defense import DefenseType
        from app.models.game.ship import ShipType

        unlocks = {}
        for key, catalogue in (('buildings', BuildingType),
                               ('ships', ShipType), ('defenses', DefenseType)):
            found = {}
            for unit in catalogue:
                required = (unit.value.get('requirements') or {}).get('technologies') or {}
                if self.name in required:
                    found[unit.name] = required[self.name]
            if found:
                unlocks[key] = found
        return unlocks

    @property
    def is_endless(self):
        return self.max_level == 0

    def is_maxed(self, level):
        """Ce niveau est-il le dernier ? Jamais vrai pour un noeud infini."""
        return not self.is_endless and level >= self.max_level

    @property
    def tier_requirement(self):
        """Niveaux a depenser dans la branche pour atteindre ce palier."""
        return TIER_REQUIREMENTS[self.tier]

    # ── Cout et duree ─────────────────────────────────────────────────────────

    def price(self, level):
        """
        Cout du niveau `level`, le premier portant le numero 1.
        ---
        `base x facteur^(level-1)` : le niveau 1 coute exactement la base. Un
        seul appelant, `Technology.can_be_increased`, qui demande toujours
        `self.level + 1` — c'est-a-dire le prochain.
        """
        exponent = max(0, level - 1)
        return {
            resource: base * pow(self.cost_factor, exponent)
            for resource, base in self.base_cost.items()
        }

    def duration(self, level, modifiers=None):
        """
        Duree pour passer de `level` a `level + 1`, en secondes.
        ---
        `base x facteur^level` : partir du niveau 0 coute exactement la base.

        `modifiers` est l'ensemble du joueur — faction et recherche empilees.
        L'ancienne signature prenait un `user` et n'allait chercher que sa
        faction, ce qui laissait `calcul` sans effet sur les durees qu'il est
        precisement cense reduire.
        """
        seconds = self.base_time * pow(self.time_factor, max(0, level))
        if modifiers is None:
            return seconds
        return modifiers.shorten(seconds, scope=ModifierScope.Technologies)

    # ── Effets ────────────────────────────────────────────────────────────────

    def modifiers_at(self, level, choice=None):
        """
        Ce que ce noeud apporte a ce niveau.
        ---
        Rien au niveau 0 : un noeud non acquis n'apporte pas la moitie de son
        bonus. Une doctrine n'apporte que la voie retenue — sans choix, elle
        n'apporte rien, meme acquise.

        :param level: niveau atteint par le joueur
        :param choice: cle de la voie retenue, pour une doctrine
        :return: liste de `Modifier`
        """
        if level <= 0:
            return []

        sources = list(self.effects)
        if self.kind == NodeKind.doctrine:
            option = self.option(choice)
            if option is None:
                return []
            sources = list(option["effects"])

        modifiers = []
        for spec in sources:
            percentage = spec["percentage"] + spec["per_level"] * level
            flat = spec["flat"] + spec["flat_per_level"] * level
            if not percentage and not flat:
                continue
            modifiers.append(Modifier(
                type=spec["type"],
                scope=spec["scope"],
                percentage=percentage,
                flat=flat,
                target=spec["target"],
                source="tech:%s" % self.name,
            ))

        # Un deblocage n'a pas de valeur, seulement une presence. Il n'est pose
        # que lorsque le niveau requis est atteint.
        for scope_name, targets in self.unlocks.items():
            scope = _UNLOCK_SCOPES.get(scope_name)
            if scope is None:
                continue
            for target, required in targets.items():
                if level >= required:
                    modifiers.append(Modifier(
                        type=ModifierType.Unlock, scope=scope, target=target,
                        source="tech:%s" % self.name))

        return modifiers

    def option(self, choice):
        """La voie retenue d'une doctrine, ou None."""
        return next((o for o in self.options if o["key"] == choice), None)

    def effect_labels(self, level, choice=None):
        """
        Les phrases a afficher, et ce qu'elles valent au niveau atteint.
        ---
        Le pourcentage courant vient du meme calcul que les modificateurs : la
        fiche ne peut donc pas annoncer autre chose que ce qui est applique.
        """
        sources = list(self.effects)
        if self.kind == NodeKind.doctrine:
            # Sans voie retenue, il n'y a rien a annoncer : montrer celle du
            # dessus la ferait passer pour l'effet du noeud, alors qu'elle n'est
            # qu'une des deux — et que l'autre dit le contraire. Les deux voies
            # se lisent cote a cote, dans `options`.
            option = self.option(choice)
            sources = list(option["effects"]) if option else []

        labels = []
        for spec in sources:
            entry = {'label': spec["label"]}
            if spec["per_level"] or spec["flat_per_level"]:
                entry['current'] = round(
                    spec["percentage"] + spec["per_level"] * level, 2)
                entry['next'] = round(
                    spec["percentage"] + spec["per_level"] * (level + 1), 2)
                if spec["flat_per_level"]:
                    entry['current_flat'] = round(
                        spec["flat"] + spec["flat_per_level"] * level, 2)
                    entry['next_flat'] = round(
                        spec["flat"] + spec["flat_per_level"] * (level + 1), 2)
            else:
                entry['current'] = spec["percentage"] if level > 0 else 0
                entry['next'] = spec["percentage"]
            labels.append(entry)
        return labels

    # ── Serialisation ─────────────────────────────────────────────────────────

    def describe(self):
        """
        Le noeud tel que le catalogue le publie : sa forme, jamais l'etat d'un
        joueur. C'est ce que les deux clients mettent en cache.
        """
        return {
            'name': self.name,
            'label': self.label,
            'summary': self.summary,
            'branch': self.branch.name,
            'tier': self.tier,
            'tier_requirement': self.tier_requirement,
            'kind': str(self.kind),
            'max_level': self.max_level,
            'endless': self.is_endless,
            'requires': dict(self.requires),
            # La meme chose en liste. Le client Unity deserialise avec
            # JsonUtility, qui ne sait pas lire un objet JSON dont les cles ne
            # sont pas connues a la compilation — et les cles de `requires` sont
            # les cent trente noms de l'arbre. La console, elle, continue de
            # lire la forme indexee : c'est celle qui se questionne bien en JS.
            'prerequisites': [
                {
                    'name': name,
                    'label': (TechnologyType.get_by_name(name).label
                              if TechnologyType.get_by_name(name) else name),
                    'level': level,
                }
                for name, level in sorted(self.requires.items())
            ],
            'base_cost': dict(self.base_cost),
            'cost_factor': self.cost_factor,
            'base_time': self.base_time,
            'time_factor': self.time_factor,
            'unlocks': {k: dict(v) for k, v in self.unlocks.items()},
            # Meme raison que `prerequisites`, a deux niveaux d'imbrication.
            'unlock_list': [
                {'kind': kind, 'name': name, 'level': level}
                for kind, found in sorted(self.unlocks.items())
                for name, level in sorted(found.items())
            ],
            'effects': [
                {
                    'type': str(e["type"]),
                    'scope': str(e["scope"]),
                    'target': e["target"],
                    'per_level': e["per_level"],
                    'percentage': e["percentage"],
                    'flat': e["flat"],
                    'flat_per_level': e["flat_per_level"],
                    'label': e["label"],
                }
                for e in self.effects
            ],
            'options': [
                {
                    'key': o["key"],
                    'label': o["label"],
                    'summary': o.get("summary", ""),
                    'effects': [
                        {'label': e["label"], 'percentage': e["percentage"],
                         'flat': e["flat"], 'type': str(e["type"]),
                         'scope': str(e["scope"]), 'target': e["target"]}
                        for e in o["effects"]
                    ],
                }
                for o in self.options
            ],
        }


#: Correspondance entre la cle rendue par `TechnologyType.unlocks` et la portee
#: du modificateur correspondant. Lue par `modifiers_at`, qui pose un `Unlock`
#: des que le niveau requis est atteint.
_UNLOCK_SCOPES = {
    'buildings': ModifierScope.Buildings,
    'ships': ModifierScope.Ships,
    'defenses': ModifierScope.Defenses,
}


#: Les sept membres d'avant, vers ce qui les remplace. Lue par la migration et
#: par `Technology.initialize` pour les comptes deja crees : un joueur ne perd
#: pas ce qu'il avait monte.
#:
#: `chemistry` devient `ogives` et `energy` devient `fission` : ce sont les
#: noeuds qui portent desormais leurs prerequis dans `DefenseType`.
LEGACY_NAMES = {
    'computer': 'calcul',
    'optical': 'optique',
    'chemistry': 'ogives',
    'alliage': 'alliages',
    'energy': 'fission',
    'distorsion': 'distorsion',
    'atom': 'atomique',
}


def technology_requirements(element):
    """
    Les technologies qu'un batiment, une coque ou une batterie reclame.

    Rendue INDEXEE, et avec le libelle deja resolu. Trois raisons, et chacune a
    coute quelque chose :

      · `JsonUtility` — le seul lecteur JSON du client Unity — apparie par nom
        de CHAMP : il ne sait pas lire `{"chantiers": 1}`. Meme lecon que
        `claim_offer` et que `technology_type.describe()` avant lui.

      · Le libelle vient d'ici parce que le nom de noeud (`chantiers`) n'est pas
        ce qu'on montre a un joueur (« Chantiers modulaires »). Le resoudre cote
        client demanderait d'avoir charge l'arbre — ce que le panneau de
        developpement n'a aucune raison de faire.

      · Le nom brut reste, parce que c'est LUI qui sert de cible : les deux
        interfaces en font un lien vers le noeud dans la vue recherche.

    Le niveau vaut toujours 1 — voir `TechnologyType.unlocks` — mais il voyage
    quand meme : les clients l'affichaient deja, et une regle se relit mieux
    dans les donnees que dans un commentaire.

    :param element: membre de `BuildingType`, `ShipType` ou `DefenseType`
    :return: [{'name': ..., 'label': ..., 'level': ...}], triee par libelle
    """
    required = (element.value.get('requirements') or {}).get('technologies') or {}

    found = []
    for name, level in required.items():
        node = TechnologyType.get_by_name(name)
        found.append({
            'name': name,
            # Un prerequis qui ne correspond a aucun noeud est un defaut de
            # table, pas une raison de casser la fiche : on montre le nom brut.
            'label': node.label if node is not None else name,
            'level': level,
        })

    return sorted(found, key=lambda entry: entry['label'])


def tree():
    """
    L'arbre entier, tel que `/api/technologies/tree` le publie.
    ---
    Une seule lecture pour les deux clients : ni la console ni le client de jeu
    ne detiennent de copie des couts, des durees ou des prerequis.
    """
    return {
        'branches': [b.serialize for b in Branch],
        'tiers': TIER_REQUIREMENTS,
        # Le meme bareme en tableau, indexe depuis zero : `tier_points[t - 1]`
        # est ce qu'il faut avoir depense dans la branche pour ouvrir le palier
        # `t`. Pour la meme raison que `prerequisites` — un objet dont les cles
        # sont des nombres ne se deserialise pas cote Unity.
        'tier_points': [TIER_REQUIREMENTS[tier]
                        for tier in sorted(TIER_REQUIREMENTS)],
        'nodes': [t.describe() for t in TechnologyType],
    }
