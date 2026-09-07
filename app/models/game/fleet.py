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

Le voyage entre systemes suit les liaisons tracees entre etoiles, saut par
saut : voir `app/models/game/starlanes.py`, qui porte cote serveur la regle de
voisinage jusque-la calculee par le seul client. Il n'y a pas de boucle de jeu
ici — un voyage avance quand on le lit, comme la production d'un territoire.

L'orbite, elle, est declaree et non deduite : `orbiting_territory_id` dit de
quelle planete une flotte tient l'orbite. Le serveur ne connait aucune
coordonnee de planete — il ne pourrait pas la deviner d'une distance — et c'est
pourtant sur cette information que se decide l'affectation d'un vaisseau qui
sort de chantier. Voir `receive_construction`.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game import starlanes
from app.models.game.settings import GalaxySettings
from app.models.game.ship import Ship
from logger import logger


#: Secondes pour parcourir une unite de carte, avant reglage de galaxie.
#: Une liaison courante mesure environ six unites : un saut prend donc six
#: minutes, du meme ordre qu'un vaisseau de ligne en chantier. Les deux se
#: comparent — decider entre construire et deplacer n'a de sens que si les
#: deux se paient dans la meme monnaie.
TRAVEL_SECONDS_PER_UNIT = 60.0


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

    # Le voyage en cours, s'il y en a un : les systemes traverses, la duree de
    # chaque saut, et l'instant du depart. Trois colonnes plutot qu'une table de
    # trajets — une flotte n'a qu'un voyage a la fois, et le chemin est fige au
    # depart : le recalculer a chaque lecture ferait changer une route sous les
    # pieds du joueur si la galaxie s'agrandissait en cours de partie.
    travel_route = Column(String, nullable=True)
    travel_legs = Column(String, nullable=True)
    travel_started_at = Column(DateTime, nullable=True)

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
    def in_galaxy(cls, galaxy_name, user=None):
        """
        Les flottes d'une galaxie entiere, celles du joueur quand on en donne un.
        ---
        Une flotte tient a un systeme, qui tient a une galaxie : c'est la portee
        de ce qu'un joueur voit d'un coup d'oeil depuis la carte. Sans elle, la
        vue galaxie devrait interroger le serveur systeme par systeme.
        """
        from app.models.game.system import System

        query = db.session.query(Fleet)\
            .join(System, Fleet.system_id == System.id)\
            .filter(System.galaxy_name == galaxy_name)
        if user is not None:
            query = query.filter(cls.user_id == user.id)
        return query.order_by(cls.system_id, cls.id).all()

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

    # -- voyage ----------------------------------------------------------------

    @classmethod
    def catch_up(cls, user):
        """
        Avance tous les voyages en cours d'un joueur.
        ---
        Le serveur n'a pas de boucle de jeu : l'etat se rattrape a la lecture,
        comme `Territory.update_view` le fait pour la production et les
        chantiers. Il faut le faire avant d'interroger les flottes d'un systeme
        et non apres : une flotte arrivee porte encore l'identifiant de celui
        qu'elle a quitte, et le filtre la rangerait au mauvais endroit.
        """
        travelling = db.session.query(Fleet)\
            .filter(cls.user_id == user.id)\
            .filter(cls.travel_route.isnot(None))\
            .all()

        for fleet in travelling:
            fleet.refresh()

        if travelling:
            db.session.flush()

        return travelling

    @property
    def route(self):
        """Les systemes traverses, du depart a la destination."""
        return json.loads(self.travel_route) if self.travel_route else []

    @property
    def legs(self):
        """La duree de chaque saut, en secondes."""
        return json.loads(self.travel_legs) if self.travel_legs else []

    @property
    def is_travelling(self):
        return bool(self.travel_route) and self.travel_started_at is not None

    def _progress(self):
        """
        Ou en est le voyage : (indice du saut en cours, secondes ecoulees
        dedans, secondes ecoulees en tout).

        L'indice vaut le nombre de sauts quand le voyage est fini.
        """
        legs = self.legs
        total = max(0.0, (datetime.utcnow() - self.travel_started_at).total_seconds())

        left = total
        for index, seconds in enumerate(legs):
            if left < seconds:
                return index, left, total
            left -= seconds

        return len(legs), 0.0, total

    def refresh(self):
        """
        Fait avancer le voyage jusqu'a l'instant present.
        ---
        La flotte appartient au dernier relais franchi : entre deux etoiles,
        c'est celle qu'elle vient de quitter. Le client, lui, sait la placer sur
        le trait grace a `travel` — mais il fallait au serveur une reponse
        simple a « dans quel systeme est-elle ? », et un point du vide n'en est
        pas une.
        """
        if not self.is_travelling:
            return False

        route = self.route
        index, _, _ = self._progress()

        if index >= len(self.legs):
            arrived_at = route[-1]
            logger.info(f"Fleet {self.id} arrived in system {arrived_at}", infos=dict(
                fleet_id=self.id,
                system_id=arrived_at,
                user_id=self.user_id,
            ))
            self.system_id = arrived_at
            self.travel_route = None
            self.travel_legs = None
            self.travel_started_at = None

            # Elle arrive dans l'espace du systeme, sans orbite et a l'origine
            # du repere : le client la posera ou il l'entend a la premiere
            # manoeuvre. Garder la position d'un autre systeme la ferait
            # apparaitre au hasard de la geometrie de celui-ci.
            self.position_x = 0.0
            self.position_y = 0.0
            self.position_z = 0.0
            self.orbiting_territory_id = None
            return True

        if self.system_id != route[index]:
            self.system_id = route[index]
            return True

        return False

    def travel_to(self, destination_id, galaxy_name):
        """
        Envoie la flotte vers un systeme, par les liaisons entre etoiles.
        ---
        Un ordre donne en vol ne fait pas demi-tour au milieu du vide : la
        flotte finit le saut commence, et le nouveau chemin part du relais
        qu'elle atteint. C'est la seule lecture qui tienne d'un espace ou l'on
        ne circule que par des liaisons — et cela evite qu'un ordre repete a
        chaque seconde fasse surplace, chaque ordre repartant du meme point.

        Rend le chemin retenu, ou None quand aucune suite de liaisons ne mene a
        la destination.
        """
        self.refresh()

        seconds_per_unit = TRAVEL_SECONDS_PER_UNIT / GalaxySettings.value(
            galaxy_name=galaxy_name, key='fleet_speed_multiplier')

        if self.is_travelling:
            index, in_leg, _ = self._progress()
            current = self.route
            legs = self.legs

            # Le relais vers lequel elle vole deja : le nouveau chemin en part.
            approaching = current[index + 1]
            remaining = max(0.0, legs[index] - in_leg)

            path = starlanes.route(
                galaxy_name=galaxy_name,
                origin_id=approaching,
                destination_id=destination_id)
            if path is None:
                return None

            lengths = starlanes.leg_lengths(galaxy_name=galaxy_name, path=path)
            new_route = [current[index]] + path
            new_legs = [remaining] + [length * seconds_per_unit for length in lengths]
        else:
            path = starlanes.route(
                galaxy_name=galaxy_name,
                origin_id=self.system_id,
                destination_id=destination_id)
            if path is None or len(path) < 2:
                return None

            lengths = starlanes.leg_lengths(galaxy_name=galaxy_name, path=path)
            new_route = path
            new_legs = [length * seconds_per_unit for length in lengths]

        if not new_legs:
            return None

        self.travel_route = json.dumps(new_route)
        self.travel_legs = json.dumps(new_legs)
        self.travel_started_at = datetime.utcnow()

        # Elle quitte l'orbite en partant. Sans cela, un chantier reste derriere
        # elle continuerait de lui livrer ses vaisseaux a l'autre bout de la
        # galaxie : c'est `orbiting_territory_id` qui decide de l'affectation,
        # voir `receive_construction`.
        self.orbiting_territory_id = None

        logger.info(f"Fleet {self.id} departing for system {new_route[-1]}", infos=dict(
            fleet_id=self.id,
            user_id=self.user_id,
            route=new_route,
            seconds=sum(new_legs),
        ))
        return new_route

    def stop_travel(self):
        """
        Annule un voyage : la flotte se pose au dernier relais franchi.
        ---
        Le dernier relais et non le point du vide ou elle se trouve : une flotte
        stationnee entre deux etoiles ne serait dans aucun systeme, et rien dans
        le modele ne sait exprimer cela.
        """
        if not self.is_travelling:
            return False

        self.refresh()
        if not self.is_travelling:
            return True

        self.system_id = self.route[self._progress()[0]]
        self.travel_route = None
        self.travel_legs = None
        self.travel_started_at = None
        return True

    @property
    def travel(self):
        """
        L'etat du voyage tel que le client en a besoin, ou None a l'arret.
        ---
        Le serveur ne sait pas placer une flotte sur la carte — il n'a pas
        l'echelle a laquelle Unity dessine la galaxie. Il donne donc les deux
        etoiles du saut en cours et la fraction parcourue entre elles : c'est au
        client d'en tirer un point, avec les positions qu'il affiche.
        """
        if not self.is_travelling:
            return None

        route = self.route
        legs = self.legs
        index, in_leg, elapsed = self._progress()

        if index >= len(legs):
            return None

        total = sum(legs)
        return {
            'route': route,
            # La duree de chaque saut, pour que le client avance la flotte tout
            # seul entre deux lectures. Sans elle il devrait interroger le
            # serveur a chaque image pour la faire bouger, ou la laisser sauter
            # d'un relais a l'autre.
            'legs': legs,
            'destination_id': route[-1],
            'from_id': route[index],
            'to_id': route[index + 1],
            'leg_index': index,
            'leg_progress': (in_leg / legs[index]) if legs[index] > 0 else 1.0,
            'seconds_left': max(0.0, total - elapsed),
            'started_at': self.travel_started_at.isoformat(),
            'arriving_at': (
                self.travel_started_at + timedelta(seconds=total)).isoformat(),
        }

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
            # Le voyage en cours, nul quand la flotte est a l'arret. Le client
            # en tire le trait de route et le temps restant.
            'travel': self.travel,
            'ships': [s.serialize for s in self.ships if s.count > 0],
            'composition': self.composition,
            'size': self.size,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
