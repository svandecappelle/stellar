"""
Flottes : ce qui porte les vaisseaux, et ce qui bouge dans un systeme.

Un vaisseau n'appartient pas a la planete qui l'a assemble. Il sort du chantier
et se retrouve dans l'espace du systeme, ou il ne tient debout qu'au sein d'une
flotte : c'est la flotte qui a une position, un cap et des ordres, jamais
l'unite isolee. Le stock reste donc un compteur par type, mais rattache a une
flotte plutot qu'a un territoire.

La position est celle du client — des coordonnees Unity du repere du systeme.
Le serveur ne la calcule pas et ne l'interprete pas : il la garde pour que la
flotte se retrouve au meme endroit a la prochaine entree dans le systeme. La
geometrie du systeme (rayons d'orbite, echelle) vit entierement cote client.

L'orbite, elle, est declaree et non deduite : `orbiting_territory_id` dit de
quelle planete une flotte tient l'orbite. Le serveur ne connait aucune
coordonnee de planete — il ne pourrait pas la deviner d'une distance — et c'est
pourtant sur cette information que se decide l'affectation d'un vaisseau qui
sort de chantier. Voir `receive_construction`.
"""

from datetime import datetime

from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.ship import Ship
from logger import logger


class Fleet(Base):
    __tablename__ = 'fleet'

    id = Column(Integer, primary_key=True)

    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=True)

    # Coordonnees Unity, dans le repere du systeme. Le plan orbital est en y=0 :
    # une flotte creee sans position s'y trouve, a l'origine, jusqu'a ce que le
    # client la pose ailleurs.
    position_x = Column(Float, nullable=False, default=0.0)
    position_y = Column(Float, nullable=False, default=0.0)
    position_z = Column(Float, nullable=False, default=0.0)

    # La planete dont la flotte tient l'orbite, nulle quand elle est en transit
    # ou stationnee dans le vide. Declaree par le client, jamais deduite.
    orbiting_territory_id = Column(Integer, ForeignKey("territory.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    ships = relationship("Ship", back_populates="fleet", cascade="all, delete-orphan")
    system = relationship("System", back_populates="fleets")
    user = relationship("User", uselist=False)
    orbiting_territory = relationship("Territory", foreign_keys=[orbiting_territory_id])

    def __init__(self, system_id, user_id, name=None, position=None, orbiting_territory_id=None):
        self.system_id = system_id
        self.user_id = user_id
        self.name = name
        self.orbiting_territory_id = orbiting_territory_id
        self.position_x = 0.0
        self.position_y = 0.0
        self.position_z = 0.0
        self.move_to(position)

    def __repr__(self):
        return '<Fleet#{} {}>'.format(self.id, self.name)

    # -- lecture ---------------------------------------------------------------

    @classmethod
    def get(cls, id, user=None):
        """
        Une flotte, restreinte a son proprietaire quand on en donne un.
        ---
        Rend None plutot que de lever : l'appelant sait mieux que ce modele si
        l'absence est un 404 ou un cas normal.
        """
        query = db.session.query(Fleet).filter(cls.id == id)
        if user is not None:
            query = query.filter(cls.user_id == user.id)
        return query.one_or_none()

    @classmethod
    def in_system(cls, system_id, user=None):
        """Les flottes d'un systeme, celles du joueur quand on en donne un."""
        query = db.session.query(Fleet).filter(cls.system_id == system_id)
        if user is not None:
            query = query.filter(cls.user_id == user.id)
        return query.order_by(cls.id).all()

    @classmethod
    def in_orbit_of(cls, territory, user=None):
        """
        Les flottes qui tiennent l'orbite de ce territoire.
        ---
        Une simple egalite sur une colonne : c'est tout l'interet d'une orbite
        declaree. Une orbite deduite d'une distance obligerait le serveur a
        connaitre la geometrie du systeme, qui n'existe que chez le client.
        """
        query = db.session.query(Fleet).filter(cls.orbiting_territory_id == territory.id)
        if user is not None:
            query = query.filter(cls.user_id == user.id)
        return query.order_by(cls.id).all()

    # -- ecriture --------------------------------------------------------------

    @classmethod
    def next_name(cls, system_id, user_id):
        """
        Nomme la prochaine flotte du joueur dans ce systeme.
        ---
        On compte les flottes existantes plutot que de reprendre le plus grand
        numero : deux flottes portant le meme nom ne genent rien, le client les
        distingue par leur identifiant.
        """
        count = db.session.query(Fleet)\
            .filter(cls.system_id == system_id)\
            .filter(cls.user_id == user_id)\
            .count()
        return "Fleet {}".format(count + 1)

    @classmethod
    def create(cls, system_id, user, name=None, position=None, orbiting_territory_id=None):
        """
        ---
        :param position: dict {x, y, z} en coordonnees Unity, ou None
        :return:
        """
        fleet = Fleet(
            system_id=system_id,
            user_id=user.id,
            name=name or cls.next_name(system_id=system_id, user_id=user.id),
            position=position,
            orbiting_territory_id=orbiting_territory_id,
        )
        db.session.add(fleet)
        db.session.flush()
        logger.info(f"Fleet {fleet.id} created", infos=dict(
            fleet_id=fleet.id,
            system_id=system_id,
            user_id=user.id,
            orbiting_territory_id=orbiting_territory_id,
        ))
        return fleet

    @classmethod
    def receive_construction(cls, territory, user, memo_fleet_id=None, spawn=None):
        """
        La flotte a laquelle revient un vaisseau qui sort de chantier.
        ---
        Un vaisseau appartient toujours a une flotte. Laquelle depend de ce qui
        se trouve en orbite de la planete au moment ou il est livre :

          - une seule flotte en orbite : elle le prend. C'est le cas courant, et
            celui qu'attend le joueur — ce qu'il assemble rejoint ce qu'il a
            deja sur place ;
          - aucune : il faut bien lui en donner une, on la cree ici, en orbite
            de la planete qui l'a produit ;
          - plusieurs : le choix ne se tranche pas tout seul, et en designer une
            au hasard reviendrait a decider a la place du joueur. Une flotte
            neuve recueille donc les sorties de chantier, a lui de fusionner.

        Une commande porte sur plusieurs unites, livrees au fil des heures : la
        flotte retenue est memorisee sur l'evenement (`fleetId`) et reprise aux
        livraisons suivantes, sans quoi une commande de dix vaisseaux creerait
        dix flottes. Elle n'est reprise que tant qu'elle tient encore cette
        orbite : une flotte partie en manoeuvre n'a plus a recevoir ce qui sort
        du chantier reste derriere elle.

        :param memo_fleet_id: la flotte deja retenue pour cette commande
        :param spawn: position Unity a donner a une flotte creee ici
        """
        if memo_fleet_id is not None:
            memo = cls.get(id=memo_fleet_id, user=user)
            if memo is not None and memo.orbiting_territory_id == territory.id:
                return memo

        in_orbit = cls.in_orbit_of(territory=territory, user=user)
        if len(in_orbit) == 1:
            return in_orbit[0]

        logger.info(
            f"Creating a fleet to receive the shipyard output of territory {territory.id}",
            infos=dict(
                territory_id=territory.id,
                fleets_in_orbit=len(in_orbit),
                user_id=user.id,
            ))
        return cls.create(
            system_id=territory.system_id,
            user=user,
            position=spawn,
            orbiting_territory_id=territory.id,
        )

    def add_ships(self, ship_type, amount):
        """
        Verse des vaisseaux dans la flotte.
        ---
        La ligne du type est creee a la demande : une flotte ne porte que les
        types qu'elle a effectivement recus, et non les sept lignes a zero que
        chaque territoire trainait auparavant.
        """
        if amount <= 0:
            return None
        ship = next((s for s in self.ships if s.type == ship_type), None)
        if ship is None:
            ship = Ship(fleet_id=self.id, type=ship_type)
            db.session.add(ship)
            self.ships.append(ship)
        ship.increment(count=amount)
        logger.info(f"Fleet {self.id} received {amount} {ship_type.name}", infos=dict(
            fleet_id=self.id,
            ship_type=ship_type.name,
            amount=amount,
            total=ship.count,
        ))
        return ship

    def move_to(self, position):
        """
        Pose la flotte a une position Unity.
        ---
        Un `None` laisse la flotte ou elle est : c'est ce que renvoie un client
        sans geometrie — la console web notamment, qui manoeuvre les flottes
        sans jamais savoir ou elles sont a l'ecran.
        """
        if position is None:
            return
        self.position_x = float(position.get('x', self.position_x or 0.0))
        self.position_y = float(position.get('y', self.position_y or 0.0))
        self.position_z = float(position.get('z', self.position_z or 0.0))

    def set_orbit(self, territory_id):
        """Amarre la flotte a une orbite, ou l'en detache avec None."""
        self.orbiting_territory_id = territory_id

    # -- lecture derivee -------------------------------------------------------

    @property
    def position(self):
        return {
            'x': self.position_x or 0.0,
            'y': self.position_y or 0.0,
            'z': self.position_z or 0.0,
        }

    @property
    def composition(self):
        """Ce que porte la flotte, par type, les lignes vides exclues."""
        return {s.type.name: s.count for s in self.ships if s.count > 0}

    @property
    def size(self):
        """Nombre de vaisseaux, tous types confondus."""
        return sum(s.count for s in self.ships)

    @property
    def is_empty(self):
        return self.size == 0

    @property
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'system_id': self.system_id,
            'user_id': self.user_id,
            # Coordonnees Unity telles que le client les a posees : c'est a lui
            # qu'elles veulent dire quelque chose.
            'position': self.position,
            'orbiting_territory_id': self.orbiting_territory_id,
            'ships': [s.serialize for s in self.ships if s.count > 0],
            'composition': self.composition,
            'size': self.size,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
