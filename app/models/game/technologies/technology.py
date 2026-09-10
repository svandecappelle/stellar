# -*- coding: utf-8 -*-

"""
L'etat de l'arbre pour un joueur : ce qu'il a monte, ce qu'il cherche.

La recherche est imperiale et l'a toujours ete — `user_technologies` pend a
`users`, pas a un territoire, et `GalaxySettings` dit noir sur blanc que les
technologies traversent les galaxies. Le code, lui, facturait un territoire et
posait un `PositionalEvent` sur lui : le stock d'un seul monde plafonnait la
recherche de tout l'empire, et deux mondes riches ne cherchaient pas plus vite
qu'un seul.

Ce qui change ici :

  · une commande de recherche se paie sur l'ensemble des mondes du joueur
    (`User.spend_empire`), et les Donnees se prennent dans la reserve imperiale
    que remplit l'academie ;
  · elle vit dans un `UserEvent`, qui est deja l'evenement d'un joueur, et non
    dans un `PositionalEvent`, qui est celui d'un lieu ;
  · plusieurs recherches tournent de front, dans la limite des emplacements
    ouverts. Ce ne sont pas des places dans une file d'attente : chacune avance
    pour son compte et finit a son heure.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import object_session, relationship

from app.application import db
from app.models.base import Base
from app.models.game.event import UserEvent, UserEventType
from app.models.game.modifiers import ModifierScope, ModifierSet, ModifierType
from app.models.game.technologies.technology_type import (
    Branch, NodeKind, TechnologyType)
from logger import logger


#: Emplacements de recherche ouverts d'office, avant toute academie.
BASE_RESEARCH_SLOTS = 1

#: Niveaux d'academie cumules sur l'empire pour en ouvrir un de plus.
ACADEMY_LEVELS_PER_SLOT = 10

#: Plafond de ce que les academies peuvent ouvrir. Au-dela, il faut la voie
#: « IA distribuee » de la doctrine d'intelligence artificielle — c'est la seule
#: chose qui la rende preferable a sa voisine.
MAX_ACADEMY_SLOTS = 4

#: Part de la depense rendue quand le joueur annule. La progression du niveau
#: en cours est perdue : annuler n'est pas gratuit, seulement moins cher que
#: laisser tourner.
CANCEL_REFUND = 0.5


class ResearchError(ValueError):
    """
    Une commande de recherche refusee, avec la raison en clair.

    Une `ValueError` nue disait « Technology X can not be increased », ce que le
    joueur voyait tel quel sans savoir s'il lui manquait un prerequis, une
    ressource ou un emplacement.
    """


class Technology(Base):
    __tablename__ = 'user_technologies'

    type = Column(Enum(TechnologyType), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)

    level = Column(Integer)

    #: Voie retenue pour une doctrine, `None` partout ailleurs. Le choix est
    #: definitif : rien dans le modele ne le reecrit une fois pose.
    choice = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="technologies")

    def __init__(self, type, user_id, level, choice=None, created_at=None, updated_at=None):
        self.type = type
        self.user_id = user_id
        self.level = level
        self.choice = choice
        if created_at:
            self.created_at = created_at
        if updated_at:
            self.updated_at = updated_at

    # ── Lecture ───────────────────────────────────────────────────────────────

    @classmethod
    def initialize(cls, user):
        """
        Poser les lignes d'un nouveau joueur, toutes a zero.
        ---
        Alias historique de `ensure`, garde parce que `User.new` l'appelle sous
        ce nom.
        """
        return cls.ensure(user)

    @classmethod
    def ensure(cls, user):
        """
        Garantir que le joueur porte une ligne par noeud de l'arbre.
        ---
        Idempotent, et appele a la lecture autant qu'a la creation. Deux trous
        se refermaient mal sans lui :

          · un compte cree SANS territoire — l'administrateur que pose
            `initialize.py` — n'avait aucune ligne, puisque `User.new` n'appelle
            `initialize` que lorsqu'un monde lui est remis. Qu'il en recoive un
            plus tard ne changeait rien : il jouait alors sans une seule
            technologie, et l'ecran de recherche n'ouvrait aucune fiche ;
          · l'arbre s'agrandit avec le code. Une migration pose les lignes
            manquantes en bloc, mais tant qu'elle n'a pas tourne le joueur voit
            des noeuds dont il n'a pas d'etat. Les poser ici fait de la migration
            une operation de confort plutot qu'une condition de fonctionnement.

        La transaction imbriquee protege l'appelant : sur Postgres, une valeur
        d'enum non declaree fait echouer l'insertion, et sans ce garde elle
        emporterait la transaction en cours — une simple LECTURE de l'arbre
        rendrait alors une erreur serveur. Le desaccord reste visible, le client
        le nomme, mais la page continue de repondre.

        :return: les noeuds effectivement ajoutes
        """
        if object_session(user) is None:
            return []

        existing = {t.type for t in cls.query(user=user).all()}
        missing = [tech for tech in TechnologyType if tech not in existing]
        if not missing:
            return []

        try:
            with db.session.begin_nested():
                for tech in missing:
                    db.session.add(Technology(type=tech, user_id=user.id, level=0))
        except Exception as error:  # noqa: BLE001 - la lecture doit survivre
            logger.warning("Could not complete the technology tree", infos=dict(
                user_id=user.id, missing=len(missing), error=str(error)))
            return []

        logger.info("Technology tree completed", infos=dict(
            user_id=user.id, added=len(missing)))
        return missing

    @classmethod
    def get(cls, user, type):
        """
        :rtype: app.models.game.technologies.technology.Technology
        """
        return cls.query(user=user, type=type).one()

    @classmethod
    def all(cls, user):
        """
        Les 36 lignes du joueur.
        ---
        Un joueur rattache a aucune session — un modele monte a la main, comme
        en font les tests de regles — n'a rien a lire en base : ce qu'on lui a
        pose en memoire est alors tout ce qu'il possede. Sans ce detour, la
        moindre lecture de production exigerait une base, alors que le calcul
        n'en demande aucune.
        """
        if object_session(user) is None:
            return list(user.technologies or [])
        return cls.query(user=user).all()

    @classmethod
    def query(cls, user, type=None):
        query = db.session.query(Technology).filter(cls.user_id == user.id)
        if type:
            query = query.filter(cls.type == type)
        return query

    @classmethod
    def levels(cls, user):
        """{nom de noeud: niveau}, pour la verification des prerequis."""
        return {t.type.name: (t.level or 0) for t in cls.all(user=user)}

    @classmethod
    def branch_levels(cls, user):
        """
        Niveaux cumules par branche : ce qui ouvre les paliers.
        ---
        Un noeud infini compte comme les autres. Il est au dernier palier, il
        n'ouvre donc rien de plus, mais rien ne justifierait de l'exclure.
        """
        totals = {branch: 0 for branch in Branch}
        for tech in cls.all(user=user):
            totals[tech.type.branch] += tech.level or 0
        return totals

    # ── Modificateurs ─────────────────────────────────────────────────────────

    @classmethod
    def modifiers(cls, user):
        """
        Ce que la recherche du joueur apporte, tous noeuds confondus.
        ---
        Reconstruit a chaque appel depuis les niveaux : rien n'est stocke, donc
        rien ne peut deriver de la table des noeuds. Changer un pourcentage dans
        `technology_type.py` suffit a changer le jeu.
        """
        modifiers = []
        for tech in cls.all(user=user):
            modifiers.extend(tech.type.modifiers_at(level=tech.level or 0, choice=tech.choice))
        return ModifierSet(modifiers)

    # ── Emplacements et recherches en cours ───────────────────────────────────

    @classmethod
    def pending(cls, user):
        """Les recherches en cours, la plus proche de sa fin en tete."""
        if object_session(user) is None:
            return []
        events = UserEvent.all(user=user, event_type=UserEventType.research)
        return sorted(events, key=lambda e: e.finishing_at)

    @classmethod
    def slots(cls, user, modifiers=None):
        """
        Recherches menables de front.
        ---
        Les academies de tous les mondes comptent ensemble : c'est le meme
        empire qui cherche. Le plafond porte sur ce que les batiments ouvrent,
        pas sur le total — la doctrine passe outre, et c'est tout son interet.
        """
        from app.models.game.buildings import BuildingType

        academy_levels = sum(
            building.level
            for territory in user.territories
            for building in territory.buildings
            if building.type == BuildingType.academy
        )
        from_academies = min(
            MAX_ACADEMY_SLOTS,
            BASE_RESEARCH_SLOTS + academy_levels // ACADEMY_LEVELS_PER_SLOT,
        )

        modifiers = modifiers if modifiers is not None else cls.modifiers(user=user)
        bonus = modifiers.flat(
            scope=ModifierScope.Research, modifier_type=ModifierType.Capacity, target="slots")
        return int(from_academies + bonus)

    @classmethod
    def catch_up(cls, user):
        """
        Encaisser les recherches arrivees a terme depuis la derniere lecture.
        ---
        Le pendant de `Territory.update_view` pour ce qui n'appartient a aucun
        territoire. Appele avant toute lecture des modificateurs du joueur :
        une recherche finie doit produire son effet meme si le joueur n'a pas
        ouvert l'ecran de recherche.

        :return: les technologies dont le niveau a monte
        """
        if object_session(user) is None:
            return []

        now = datetime.utcnow()
        finished = [e for e in cls.pending(user=user) if e.finishing_at <= now]
        if not finished:
            return []

        increased = []
        for event in finished:
            args = event.extra_args
            tech_type = TechnologyType.get_by_name(args.get('type'))
            if tech_type is None:
                # Un noeud retire de la table entre la commande et sa fin :
                # l'evenement est classe, rien n'est monte, rien n'est rendu.
                logger.warning("Unknown technology finished, dropping event", infos=dict(
                    user_id=user.id, type=args.get('type')))
                event.archived_at = now
                continue

            technology = cls.get(user=user, type=tech_type)
            technology.level = (technology.level or 0) + 1
            if args.get('choice') and not technology.choice:
                technology.choice = args['choice']
            event.archived_at = now
            increased.append(technology)

            logger.info("Research completed", infos=dict(
                user_id=user.id, type=tech_type.name, level=technology.level))

        db.session.flush()
        return increased

    # ── Commande ──────────────────────────────────────────────────────────────

    @property
    def next_level(self):
        """Le niveau que la prochaine recherche apporterait."""
        return (self.level or 0) + 1

    def cost(self, modifiers=None):
        """
        Ce que coute le niveau suivant, reductions comprises.
        ---
        Un seul endroit, lu par la verification comme par la serialisation : le
        joueur paie ce qui lui est annonce. C'est la lecon de `Building.cost`.
        """
        cost = self.type.price(self.next_level)
        if modifiers is None:
            return cost
        return modifiers.apply_cost(cost, scope=ModifierScope.Technologies)

    def duration(self, modifiers=None):
        """Duree du niveau suivant, en secondes."""
        return self.type.duration(level=self.level or 0, modifiers=modifiers)

    def missing_requirements(self, levels=None, branch_totals=None):
        """
        Ce qui manque pour lancer ce niveau, cote arbre uniquement.
        ---
        Deux barrieres, et elles ne se paient ni l'une ni l'autre :

          · les prerequis nommes du noeud, qui traversent les branches ;
          · le palier, ouvert par les niveaux deja depenses dans SA branche.

        :return: liste de dictionnaires decrivant chaque manque, vide si la
            voie est libre
        """
        levels = levels if levels is not None else Technology.levels(user=self.user)
        branch_totals = (
            branch_totals if branch_totals is not None
            else Technology.branch_levels(user=self.user))

        missing = []
        for name, required in self.type.requires.items():
            held = levels.get(name, 0)
            if held < required:
                node = TechnologyType.get_by_name(name)
                missing.append({
                    'kind': 'technology',
                    'name': name,
                    'label': node.label if node else name,
                    'required': required,
                    'held': held,
                })

        spent = branch_totals.get(self.type.branch, 0)
        needed = self.type.tier_requirement
        if spent < needed:
            missing.append({
                'kind': 'tier',
                'name': self.type.branch.name,
                'label': self.type.branch.label,
                'required': needed,
                'held': spent,
            })

        return missing

    def can_be_increased(self, modifiers=None, raises=False):
        """
        Ce niveau peut-il etre lance maintenant ?
        ---
        Quatre refus possibles, dans l'ordre ou ils comptent pour le joueur :
        le noeud est au maximum, il est deja en recherche, l'arbre le ferme
        encore, ou l'empire n'a pas de quoi le payer.

        :param raises: lever `ResearchError` avec la raison plutot que rendre
            False. L'API veut la phrase, l'affichage veut le booleen.
        """
        def refuse(message):
            if raises:
                raise ResearchError(message)
            return False

        if self.type.is_maxed(self.level or 0):
            return refuse("%s est déjà au niveau maximum." % self.type.label)

        if any(e.extra_args.get('type') == self.type.name
               for e in Technology.pending(user=self.user)):
            return refuse("%s est déjà en recherche." % self.type.label)

        missing = self.missing_requirements()
        if missing:
            return refuse("%s : %s" % (
                self.type.label,
                ", ".join(
                    "%s %d requis (vous avez %d)" % (m['label'], m['required'], m['held'])
                    for m in missing)))

        modifiers = modifiers if modifiers is not None else self.user.modifiers
        if not self.user.can_afford(self.cost(modifiers=modifiers)):
            return refuse("Ressources insuffisantes pour %s." % self.type.label)

        return True

    def increase(self, now=False, choice=None):
        """
        Lancer la recherche du niveau suivant.
        ---
        `now` monte le niveau sans rien facturer : c'est une faveur — une avance
        de partie, un avantage de faction — pas un achat. La recherche lancee
        par le joueur passe par l'autre branche, et se paie a la commande comme
        un batiment : c'est le moment ou il a montre qu'il en avait les moyens.

        :param choice: voie retenue, obligatoire sur une doctrine et refusee
            partout ailleurs
        """
        if now:
            # Une faveur n'a pas a choisir de voie : une doctrine offerte sans
            # voie ne rend rien (`modifiers_at` le dit), et l'exiger ici
            # empecherait d'offrir l'arbre entier d'un coup — ce que font les
            # avances de partie et les tests de faction.
            choice = self._validated_choice(choice, required=False)
            self.level = self.next_level
            if choice:
                self.choice = choice
            return None

        choice = self._validated_choice(choice)
        modifiers = self.user.modifiers
        self.can_be_increased(modifiers=modifiers, raises=True)

        if Technology.slots(user=self.user, modifiers=modifiers) <= len(
                Technology.pending(user=self.user)):
            raise ResearchError(
                "Tous vos emplacements de recherche sont occupés. "
                "Montez une académie ou annulez une recherche en cours.")

        cost = self.cost(modifiers=modifiers)
        paid = self.user.spend_empire(cost)
        duration = self.duration(modifiers=modifiers)

        logger.info("Research ordered", infos=dict(
            user_id=self.user_id, type=self.type.name,
            level=self.next_level, duration=duration))

        return UserEvent.create(
            user=self.user,
            duration=duration,
            event_type=UserEventType.research,
            extra_args={
                'type': self.type.name,
                'label': self.type.label,
                'branch': self.type.branch.name,
                'level': self.next_level,
                'choice': choice,
                # Ce qui a ete reellement debite, monde par monde : c'est la
                # seule facon de rendre a l'annulation ce qui a ete pris, et
                # aux bons endroits.
                'paid': paid,
            },
        )

    def _validated_choice(self, choice, required=True):
        """
        La voie retenue, verifiee contre la nature du noeud.
        ---
        Une doctrine sans voie est une commande incomplete ; une voie sur un
        rang est une commande qui se trompe de noeud. Les deux sont refusees
        plutot que silencieusement ignorees.

        :param required: exiger une voie sur une doctrine. Faux pour un niveau
            offert, qui n'est pas une commande du joueur.
        """
        if self.type.kind != NodeKind.doctrine:
            if choice:
                raise ResearchError("%s n'est pas une doctrine." % self.type.label)
            return None

        if not choice:
            if not required:
                return None
            raise ResearchError(
                "%s demande de choisir une voie : %s." % (
                    self.type.label,
                    " ou ".join(o['label'] for o in self.type.options)))

        if self.type.option(choice) is None:
            raise ResearchError("Voie inconnue pour %s : %r." % (self.type.label, choice))

        return choice

    @classmethod
    def cancel(cls, user, event_id):
        """
        Annuler une recherche en cours et rendre la moitie de la depense.
        ---
        Rendue la ou elle a ete prise : `paid` porte le detail par monde, et un
        remboursement au hasard deplacerait discretement des ressources d'un
        bout de l'empire a l'autre.
        """
        event = next(
            (e for e in cls.pending(user=user) if e.id == event_id), None)
        if event is None:
            raise ResearchError("Cette recherche n'est pas en cours.")

        args = event.extra_args
        user.refund_empire(args.get('paid') or {}, ratio=CANCEL_REFUND)
        event.archived_at = datetime.utcnow()

        logger.info("Research cancelled", infos=dict(
            user_id=user.id, type=args.get('type'), event_id=event_id))
        return event

    # ── Serialisation ─────────────────────────────────────────────────────────

    def serialize_for(self, modifiers, levels, branch_totals, pending):
        """
        L'etat de ce noeud pour ce joueur.
        ---
        Prend ce qu'il lui faut en argument plutot que de le relire : la vue
        serialise 36 noeuds d'affilee, et chacun aurait sinon relu les niveaux
        et les recherches en cours de tout l'empire.

        :param pending: {nom de noeud: arguments de l'evenement en cours}
        """
        level = self.level or 0
        maxed = self.type.is_maxed(level)
        missing = self.missing_requirements(levels=levels, branch_totals=branch_totals)
        ordered = pending.get(self.type.name)
        researching = ordered is not None

        # La voie retenue, ou celle qui a ete commandee et n'est pas encore
        # acquise : le joueur doit voir laquelle tourne, pas une fiche muette
        # pendant les deux jours que dure une doctrine.
        choice = self.choice or (ordered or {}).get('choice')

        if maxed:
            state = 'maxed'
        elif researching:
            state = 'researching'
        elif missing:
            state = 'locked'
        elif level > 0:
            state = 'owned'
        else:
            state = 'available'

        data = {
            'type': self.type.name,
            'label': self.type.label,
            'branch': self.type.branch.name,
            'tier': self.type.tier,
            'kind': str(self.type.kind),
            'level': level,
            'max_level': self.type.max_level,
            'state': state,
            'choice': choice,
            'missing': missing,
            'effects': self.type.effect_labels(level=level, choice=choice),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

        # Un noeud au maximum n'a ni cout ni duree : les annoncer laisserait
        # croire qu'il reste un niveau a prendre.
        if not maxed:
            data['cost'] = {
                str(resource): amount
                for resource, amount in self.cost(modifiers=modifiers).items()
            }
            data['duration'] = self.duration(modifiers=modifiers)

        return data

    @property
    def serialize(self):
        """
        Forme courte, pour les appelants qui n'ont pas prepare le contexte.
        ---
        `/api/technologies` passe par `serialize_for` : cette version-ci relit
        tout pour un seul noeud, et ne vaut que pour une lecture isolee.
        """
        return self.serialize_for(
            modifiers=self.user.modifiers,
            levels=Technology.levels(user=self.user),
            branch_totals=Technology.branch_levels(user=self.user),
            pending={
                e.extra_args.get('type'): e.extra_args
                for e in Technology.pending(user=self.user)},
        )
