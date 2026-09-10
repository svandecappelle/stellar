# -*- coding: utf-8 -*-

"""
Modificateurs : l'unique facon dont quelque chose modifie une valeur du jeu.

Une faction en pose deux ou trois a l'inscription, l'arbre technologique en
pose autant que le joueur a monte de niveaux. Les deux disaient la meme chose
et n'avaient aucune raison de le dire deux fois : ce module tient le
vocabulaire, la composition et le point d'application, et `Faction` comme
`Technology` ne sont plus que des sources.

Trois regles, et elles expliquent la forme du fichier :

  · un modificateur ne sait pas d'ou il vient. Rien ici ne mentionne ni faction
    ni technologie, sans quoi il faudrait un cas par source a chaque
    application ;
  · un pourcentage dit toujours ce qu'il fait A LA VALEUR modifiee, jamais au
    concept qui nomme son type. `-15` sur un cout le baisse, `-10` sur une duree
    la raccourcit, `+4` sur une production l'augmente. Une seule regle de signe
    pour toute la table, sans exception a retenir ;
  · les pourcentages d'une meme portee s'additionnent, ils ne se composent pas.
    Deux fois +10 % font +20 %, pas +21 %. C'est ce que le joueur lit dans la
    fiche d'un noeud, et une composition ferait diverger l'affichage du calcul
    des le troisieme bonus ;
  · un multiplicateur ne descend jamais sous `FLOOR`. Un cumul de reductions
    pourrait sinon rendre une duree nulle ou un cout negatif — le premier rend
    tout gratuit, le second cree des ressources.
"""

import enum

from logger import logger


#: Plancher d'un multiplicateur, quelle que soit la pile de reductions.
#: 5 % de la valeur de base : une recherche a -95 % reste une recherche.
FLOOR = 0.05


class ModifierType(enum.Enum):
    """
    Ce qu'un modificateur change.

    Les cinq premiers portent les noms exacts de l'ancien
    `FactionAdvantageType` : ils sont ecrits tels quels dans la colonne
    `faction_advantages.advantage_type` des bases deja en service, et les
    renommer les rendrait illisibles.
    """

    Cost = "cost"                # ce qu'une chose coute a la commande
    Power = "power"              # ce qu'une arme inflige
    Production = "production"    # ce qu'une source rend par heure
    Resistance = "resistance"    # ce qu'une coque encaisse
    TimeReduce = "time_reduce"   # ce qu'une construction ou une etude dure

    Capacity = "capacity"        # ce qu'un reservoir ou une file peut tenir
    Speed = "speed"              # ce qu'une flotte parcourt par seconde
    Unlock = "unlock"            # ce qui devient constructible

    def __str__(self):
        return self.name


class ModifierScope(enum.Enum):
    """
    Sur quoi il porte. Meme contrainte de nommage que ci-dessus pour les cinq
    premiers.
    """

    Resource = "resources"
    Ships = "ships"
    Buildings = "buildings"
    Defenses = "defenses"
    Technologies = "technologies"

    Fleet = "fleet"
    Territory = "territory"
    Research = "research"

    def __str__(self):
        return self.name


#: Cibles collectives acceptees par `target`. Une cible litterale est comparee
#: telle quelle ; ces trois-la designent un ensemble.
ANY = "*"
MATERIALS = "*materials"
STOCKS = "*stocks"


class Modifier(object):
    """
    Un effet, deja resolu au niveau atteint.

    `percentage` est signe, et son signe porte sur la VALEUR modifiee : `-10`
    retire dix pour cent, quel que soit le type. C'est la convention que portait
    deja `FactionAdvantages`, et la seule qui permette a une reduction et a un
    bonus de s'additionner sans cas particulier.

    `flat` s'ajoute apres le pourcentage, pour ce qui se compte en unites et non
    en proportion : des emplacements de file de recherche, des points
    d'habitabilite.
    """

    __slots__ = ("type", "scope", "percentage", "flat", "target", "source")

    def __init__(self, type, scope, percentage=0.0, flat=0.0, target=None, source=None):
        self.type = type
        self.scope = scope
        self.percentage = float(percentage or 0.0)
        self.flat = float(flat or 0.0)
        #: Nom de ressource, de batiment, de vaisseau — ou l'un des ensembles
        #: ci-dessus. None vaut « tout ce qui entre dans la portee ».
        self.target = target
        #: D'ou il vient, pour l'affichage et les journaux uniquement. Aucun
        #: calcul ne le lit.
        self.source = source

    def matches(self, target):
        """
        Ce modificateur porte-t-il sur cette cible precise ?
        ---
        Un modificateur sans cible porte sur toute sa portee. Un modificateur
        cible, en revanche, ne s'applique qu'a une demande qui nomme sa cible :
        une demande sans cible ne le retient pas. C'est ce que faisait deja
        `Faction.apply`, et l'inverse ferait payer le bonus silicium des
        Technocrates a toutes les ressources a la fois.
        """
        if self.target in (None, ANY):
            return True
        if target is None:
            return False

        target = str(target)

        if self.target == MATERIALS:
            from app.models.game.territory import ResourceType
            return target in {r.name for r in ResourceType.materials()}
        if self.target == STOCKS:
            from app.models.game.territory import ResourceType
            return target in {r.name for r in ResourceType.stocks()}

        return self.target == target

    @property
    def serialize(self):
        data = {
            'type': str(self.type),
            'scope': str(self.scope),
            'target': self.target,
        }
        if self.percentage:
            data['percentage'] = round(self.percentage, 4)
        if self.flat:
            data['flat'] = round(self.flat, 4)
        if self.source:
            data['source'] = self.source
        return data

    def __repr__(self):
        return "<Modifier {} {} {} {:+g}%>".format(
            self.type, self.scope, self.target or ANY, self.percentage)


class ModifierSet(object):
    """
    Une collection de modificateurs, et la seule facon de les appliquer.

    Construite a la volee — elle n'est jamais persistee. Ce qui est persiste,
    ce sont les niveaux de technologie et les lignes d'avantage de faction ;
    l'ensemble s'en deduit a chaque lecture.
    """

    def __init__(self, modifiers=None):
        self.modifiers = list(modifiers or [])

    def __iter__(self):
        return iter(self.modifiers)

    def __len__(self):
        return len(self.modifiers)

    def __add__(self, other):
        return ModifierSet(self.modifiers + list(other))

    def extend(self, modifiers):
        self.modifiers.extend(modifiers)
        return self

    def select(self, scope, modifier_type=None, target=None):
        """Les modificateurs concernes par une demande."""
        return [
            m for m in self.modifiers
            if m.scope == scope
            and (modifier_type is None or m.type == modifier_type)
            and m.matches(target)
        ]

    def percentage(self, scope, modifier_type=None, target=None):
        """Somme signee des pourcentages retenus, en points."""
        return sum(m.percentage for m in self.select(scope, modifier_type, target))

    def flat(self, scope, modifier_type=None, target=None):
        """Somme des termes constants retenus."""
        return sum(m.flat for m in self.select(scope, modifier_type, target))

    def factor(self, scope, modifier_type=None, target=None):
        """
        Le multiplicateur a appliquer, deja borne.

        Sorti a part parce que le client l'affiche : la fiche d'un noeud annonce
        « x0,86 sur la duree des recherches », et cette valeur doit etre la meme
        que celle qui sert au calcul.
        """
        return max(FLOOR, 1.0 + self.percentage(scope, modifier_type, target) / 100.0)

    def apply(self, value, scope, modifier_type=None, target=None):
        """
        Appliquer les modificateurs a une valeur.
        ---
        Pourcentage d'abord, terme constant ensuite : un +2 emplacements ne doit
        pas etre multiplie par un bonus de rendement qui n'a rien a voir.

        :param value: la valeur de base
        :param scope: portee, membre de `ModifierScope`
        :param modifier_type: type attendu, ou None pour tous les types de la
            portee — a n'utiliser que la ou un seul type peut s'appliquer
        :param target: ressource, batiment ou unite precise, ou None
        """
        if not self.modifiers:
            return value

        selected = self.select(scope, modifier_type, target)
        if not selected:
            return value

        percentage = sum(m.percentage for m in selected)
        flat = sum(m.flat for m in selected)
        result = value * max(FLOOR, 1.0 + percentage / 100.0) + flat

        logger.debug("Modifiers applied", infos=dict(
            scope=str(scope),
            modifier_type=str(modifier_type) if modifier_type else None,
            target=target,
            percentage=percentage,
            flat=flat,
            before=value,
            after=result,
        ))
        return result

    def shorten(self, seconds, scope, target=None):
        """
        Appliquer les modificateurs de duree a un delai.
        ---
        Un raccourci nomme, et rien de plus : c'est `apply` restreint a
        `TimeReduce`. Il existe parce que les appelants sont nombreux — chantier
        de batiment, assemblage de vaisseau, recherche — et qu'aucun ne doit
        avoir a se rappeler quel type filtrer.

        Le signe suit la regle commune du module : un pourcentage dit ce qu'il
        fait A LA VALEUR, pas au concept qui nomme le type. `-10` sur une duree
        la raccourcit de dix pour cent, exactement comme `-15` sur un cout le
        baisse de quinze. C'est la convention que portait deja
        `FactionAdvantages` — les Technocrates cherchent plus vite avec `-10` —
        et l'inverser pour le seul `TimeReduce` aurait donne deux conventions
        opposees dans la meme table.
        """
        return self.apply(
            seconds, scope=scope, modifier_type=ModifierType.TimeReduce, target=target)

    def apply_cost(self, cost, scope):
        """
        Appliquer une reduction de cout a un dictionnaire de couts.
        ---
        Les cles sont laissees telles quelles : elles arrivent tantot en
        `ResourceType`, tantot en chaine, selon qu'on vienne d'un batiment ou
        d'un vaisseau, et ce module n'a pas a trancher ce debat.
        """
        modifiers = self.select(scope, ModifierType.Cost)
        if not modifiers:
            return cost

        return {
            resource: self.apply(
                amount, scope=scope, modifier_type=ModifierType.Cost,
                target=str(resource))
            for resource, amount in cost.items()
        }

    def unlocked(self, scope, target):
        """
        Ce deblocage est-il acquis ?
        ---
        Un `Unlock` n'a ni pourcentage ni terme constant : sa seule presence est
        l'information.
        """
        return bool(self.select(scope, ModifierType.Unlock, target=target))

    @property
    def serialize(self):
        return [m.serialize for m in self.modifiers]


#: L'ensemble vide, pour les appelants qui n'ont pas de joueur sous la main
#: (un monde sans proprietaire, un territoire lu hors session).
NO_MODIFIERS = ModifierSet()
