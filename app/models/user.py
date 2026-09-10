from datetime import datetime

from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.event import PositionalEvent, UserEvent
from app.models.game.modifiers import ModifierSet
from app.models.game.technologies.technology import Technology
from app.models.role import Role
# Importe pour son effet : sans lui, SQLAlchemy n'enregistre pas la table
# des jetons et `create_all` ne la pose pas.
from app.models.token import DeviceToken  # noqa: F401
from app.security import (
    hash_password, needs_rehash, verify_password)
from logger import logger


#: Ressources qu'un cout reclame sans jamais les consommer. Meme liste que
#: `Territory.NON_CONSUMABLE`, et pour les memes raisons : l'energie est un
#: solde et non un stock, la population sert sans etre brulee.
NON_CONSUMABLE = ('energy', 'population')


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    email = Column(String)

    faction_id = Column(Integer, ForeignKey("factions.id"), nullable=True)

    #: Donnees : la reserve de recherche, la seule ressource qui ne pend pas a
    #: un monde. Elle est produite par les academies de tous les territoires et
    #: depensee par l'arbre technologique, qui est imperial lui aussi. En
    #: flottant parce qu'elle se credite par fractions d'heure : un entier
    #: tronquerait la production de qui se connecte souvent.
    research = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("Role", back_populates="user")
    tokens = relationship("DeviceToken", back_populates="user")
    technologies = relationship("Technology", back_populates="user")
    territories = relationship("Territory", back_populates="user")
    faction = relationship("Faction")

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def __repr__(self):
        return '<username {}>'.format(self.username)

    @classmethod
    def exists(cls, username):
        """
        Check if user exists
        """
        return db.session.query(User).filter(cls.username == username).first() is not None

    @classmethod
    def get(cls, username):
        """
        Get user object
        """
        return db.session.query(User).filter(cls.username == username).one()

    @classmethod
    def new(cls, username, password, email, territory=None):
        usr = cls(username=username, email=email)
        usr.set_password(password)
        db.session.add(usr)

        db.session.flush()
        if territory:  # If no territory the user is not a playable user (Moderator / Administrator)
            territory.assign(user=usr)
            Technology.initialize(usr)
        return usr

    def set_password(self, plain):
        """
        Range un nouveau mot de passe.
        ---
        Passe par `app.security` et non par un calcul pose ici : c'est la seule
        facon que l'inscription, le changement de mot de passe et le
        rehachage silencieux emploient tous les trois le meme.
        """
        self.password = hash_password(plain)

    def check_password(self, plain):
        """
        Ce mot de passe est-il le bon ? Le remet a jour au passage si besoin.
        ---
        Les anciens comptes portent une empreinte SHA-256 nue, sans sel et sans
        cout. On ne peut pas la convertir : une empreinte ne se remonte pas. Le
        seul instant ou le serveur tient le mot de passe en clair est celui-ci,
        et c'est donc ici que la conversion se fait — une fois, sans que le
        joueur ait rien a faire.

        L'appelant valide la session : c'est lui qui decide du `commit`.
        """
        if not verify_password(self.password, plain):
            return False

        if needs_rehash(self.password):
            self.set_password(plain)
            logger.info("Password rehashed", infos=dict(user_id=self.id))

        return True

    def add_role(self, role_type, scope="*"):
        """
        Add a specific role to the user:
        ---
        :param role_type: Role type
        :param scope: scope of action
        """
        role = Role.create(user=self, role_type=role_type, scope=scope)
        self.roles.append(role)

    def has_role(self, role_type, scope=None):
        """
        Ce joueur porte-t-il ce role, ici ?
        ---
        :param role_type: RoleType attendu
        :param scope: portee demandee — un nom de galaxie, ou None pour « ou que
                      ce soit ». Un role de portee '*' vaut partout : c'est
                      ainsi qu'est pose le role d'administrateur.
        """
        for role in self.roles:
            if role.deleted_at is not None:
                continue
            if role.role_type != role_type.value:
                continue
            if role.scope == "*" or scope is None or role.scope == scope:
                return True
        return False

    def moderates(self, galaxy_name):
        """
        Peut-il regler cette galaxie ?
        ---
        Le createur de la galaxie en est moderateur ; un administrateur les
        modere toutes, sa portee etant '*'.
        """
        from app.models.role import RoleType

        return (
            self.has_role(RoleType.admin)
            or self.has_role(RoleType.moderator, scope=galaxy_name)
        )

    def affect_faction(self, faction):
        """
        ---
        """
        self.faction = faction
        self._modifiers = None

    # ── Modificateurs ─────────────────────────────────────────────────────────

    @property
    def modifiers(self):
        """
        Tout ce qui modifie une valeur pour ce joueur : sa faction, sa recherche.
        ---
        Les deux sources parlent le meme langage depuis `modifiers.py`, et se
        lisent donc dans un seul ensemble. Un appelant n'a plus a se demander
        s'il doit interroger la faction, l'arbre, ou les deux — la question
        n'avait qu'une bonne reponse et elle etait facile a oublier.

        Memorise sur l'instance : `get_hourly_gain` est appele une fois par
        ressource et par batiment, et reconstruire trente-six noeuds a chaque
        passage couterait plus cher que la production qu'on calcule. La memoire
        ne survit pas a la requete, ce qui est exactement sa portee utile.

        Les recherches arrivees a terme sont encaissees ici, avant la lecture :
        un niveau acquis pendant que le joueur regardait ailleurs doit produire
        son effet des la premiere valeur calculee, sans attendre qu'il ouvre
        l'ecran de recherche.
        """
        cached = getattr(self, '_modifiers', None)
        if cached is not None:
            return cached

        Technology.catch_up(user=self)

        modifiers = ModifierSet()
        if self.faction:
            modifiers.extend(self.faction.modifiers)
        modifiers.extend(Technology.modifiers(user=self).modifiers)

        self._modifiers = modifiers
        return modifiers

    def forget_modifiers(self):
        """
        Oublier l'ensemble memorise.
        ---
        A appeler apres tout ce qui monte un niveau : sans cela, la valeur lue
        juste apres une recherche terminee serait encore celle d'avant.
        """
        self._modifiers = None

    # ── Reserves de l'empire ──────────────────────────────────────────────────

    @property
    def empire_resources(self):
        """
        Ce que l'empire detient, tous mondes confondus.
        ---
        Les Donnees viennent de la reserve du joueur, tout le reste de la somme
        des stocks. C'est ce que la recherche regarde : elle appartient au
        joueur, et ne peut donc pas etre plafonnee par le monde qui se trouve
        ouvert a l'ecran.
        """
        from app.models.game.territory import ResourceType

        pool = {r.name: 0.0 for r in ResourceType.stocks()}
        for territory in self.territories:
            for resource in ResourceType.stocks():
                pool[resource.name] += getattr(territory, resource.name, 0) or 0
        pool[ResourceType.research.name] = float(self.research or 0.0)
        return pool

    def can_afford(self, cost):
        """
        L'empire peut-il payer ce cout ?
        ---
        Les cles arrivent tantot en `ResourceType`, tantot en chaine selon
        l'appelant : elles sont normalisees ici plutot qu'a chaque site d'appel.
        """
        pool = self.empire_resources
        for resource, amount in cost.items():
            name = str(resource)
            if name in NON_CONSUMABLE or not amount:
                continue
            if pool.get(name, 0) < amount:
                return False
        return True

    def spend_empire(self, cost):
        """
        Debiter un cout sur l'ensemble de l'empire.
        ---
        Les Donnees sortent de la reserve du joueur ; le reste est pris monde
        par monde, du plus fourni au plus pauvre. Prendre au plus riche d'abord
        est le seul ordre qui ne vide pas un avant-poste pour une recherche que
        la capitale pouvait payer seule.

        :return: le detail de ce qui a ete pris, pour pouvoir le rendre —
            `{'research': x, 'territories': {id: {ressource: montant}}}`
        """
        from app.models.game.territory import ResourceType

        paid = {'research': 0.0, 'territories': {}}

        def note(territory, name, amount):
            key = str(territory.id)
            paid['territories'].setdefault(key, {})
            paid['territories'][key][name] = paid['territories'][key].get(name, 0) + amount

        for resource, amount in cost.items():
            name = str(resource)
            if not amount or name in NON_CONSUMABLE:
                continue

            if name == ResourceType.research.name:
                self.research = float(self.research or 0.0) - amount
                paid['research'] += amount
                continue

            remaining = amount
            richest = sorted(
                self.territories,
                key=lambda t: getattr(t, name, 0) or 0,
                reverse=True)
            for territory in richest:
                if remaining <= 0:
                    break
                held = getattr(territory, name, 0) or 0
                if held <= 0:
                    continue
                taken = min(held, remaining)
                setattr(territory, name, held - taken)
                note(territory, name, taken)
                remaining -= taken

            # Ce qui reste apres avoir vide tous les mondes : `can_afford` a
            # laisse passer une commande que l'empire ne pouvait pas honorer.
            # On le note plutot que de le taire, et le monde le plus riche part
            # en negatif comme le ferait un territoire seul.
            if remaining > 0 and richest:
                logger.warning("Empire short on resource while spending", infos=dict(
                    user_id=self.id, resource=name, missing=remaining))
                fallback = richest[0]
                setattr(fallback, name, (getattr(fallback, name, 0) or 0) - remaining)
                note(fallback, name, remaining)

        logger.info("Empire spending", infos=dict(user_id=self.id, paid=paid))
        return paid

    def refund_empire(self, paid, ratio=1.0):
        """
        Rendre une part de ce qui a ete pris, la ou ca a ete pris.
        ---
        `paid` est ce qu'a rendu `spend_empire`. Un monde cede ou perdu entre
        temps n'est plus rembourse : la ressource n'aurait nulle part ou aller,
        et la creer ailleurs deplacerait discretement l'empire.
        """
        if not paid:
            return

        self.research = float(self.research or 0.0) + (paid.get('research', 0) or 0) * ratio

        by_id = {str(t.id): t for t in self.territories}
        for territory_id, resources in (paid.get('territories') or {}).items():
            territory = by_id.get(str(territory_id))
            if territory is None:
                continue
            for name, amount in resources.items():
                setattr(territory, name, (getattr(territory, name, 0) or 0) + amount * ratio)

    def add_research(self, amount):
        """
        Crediter la reserve de Donnees.
        ---
        Le seul point ou elle grossit : c'est ici que se pose le journal qui
        permet de retrouver ce qui l'a remplie.
        """
        if amount <= 0:
            return
        self.research = float(self.research or 0.0) + amount

    @property
    def events(self):
        """
        ---
        :return:
        """
        return {
            'positional': PositionalEvent.all(user=self),
            'general': UserEvent.all(user=self)
        }

    def serialize(self, without_rights=True):
        data = {
            'id': self.id,
            'username': str(self.username).strip(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.created_at.isoformat()
        }
        if not without_rights:
            data['roles'] = [role.serialize for role in self.roles]

        return data
