import functools
import json
from datetime import datetime
import enum
import math

from sqlalchemy import Column, Enum, Integer, JSON, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType, Building
from app.models.game.community.faction import FactionAdvantageScope
from app.models.game.defense import Defense, DefenseType
from app.models.game.event import PositionalEventType, PositionalEvent
from app.models.game.planet import PlanetArchetype
from app.models.game.ship import Ship, ShipType
from app.models.game.system import System
from logger import logger


class ResourceType(enum.Enum):
    # Raw materials, extracted by the mater_extractor. Which of them a given
    # territory can produce at all depends on its planet archetype.
    iron = "iron"
    carbon = "carbon"
    silicium = "silicium"
    titanium = "titanium"
    cristal = "cristal"
    uranium = "uranium"
    hydrogen = "hydrogen"
    neutronium = "neutronium"

    # Produced by dedicated buildings, not by extraction.
    credits = "credits"
    energy = "energy"
    population = "population"
    tritium = "tritium"

    def __str__(self):
        # Without this, `str(ResourceType.iron)` yields "ResourceType.iron" and
        # every serialized cost/gain key carries the class prefix, which no
        # client can map onto a field name.
        return self.name

    @classmethod
    def materials(cls):
        """Extractable materials, in display order."""
        return [
            cls.iron, cls.carbon, cls.silicium, cls.titanium,
            cls.cristal, cls.uranium, cls.hydrogen, cls.neutronium,
        ]

    @classmethod
    def stocks(cls):
        """Resources persisted as a column on the territory."""
        return cls.materials() + [cls.credits, cls.population, cls.tritium]


class Territory(Base):
    __tablename__ = 'territory'

    id = Column(Integer, primary_key=True)

    position_in_system = Column(Integer, nullable=False)
    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    name = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    iron = Column(Integer, default=10000, nullable=False)
    carbon = Column(Integer, default=4000, nullable=False)
    silicium = Column(Integer, default=2500, nullable=False)
    titanium = Column(Integer, default=0, nullable=False)
    cristal = Column(Integer, default=0, nullable=False)
    uranium = Column(Integer, default=0, nullable=False)
    hydrogen = Column(Integer, default=0, nullable=False)
    neutronium = Column(Integer, default=0, nullable=False)

    credits = Column(Integer, default=8000, nullable=False)
    tritium = Column(Integer, default=100, nullable=False)
    population = Column(Integer, default=100, nullable=False)

    # Planet archetype: decides which materials can be extracted here.
    archetype = Column(Enum(PlanetArchetype), nullable=True)
    # Per-material richness drawn at creation: {"iron": 1.12, ...}
    deposits = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # We use json as text here to be sure compatible with all dbs.
    # This should not be necessary to query rows using this field
    characteristics = Column(JSON, nullable=True)

    buildings = relationship("Building", back_populates="territory")
    ships = relationship("Ship", back_populates="territory")
    defenses = relationship("Defense", back_populates="territory")

    system = relationship("System", back_populates="territories")
    territory_events = relationship(
        "PositionalEvent", 
        primaryjoin="and_(PositionalEvent.on_territory_id == Territory.id, PositionalEvent.archived_at == None)",
    )
    user = relationship("User", back_populates="territories")

    #: Resources that accrue over time. Population has no producer yet.
    PRODUCED_RESOURCES = ResourceType.materials() + [ResourceType.credits, ResourceType.tritium]

    def __init__(self, system, position_in_system, characteristics={}, archetype=None):
        self.system_id = system.id
        self.position_in_system = position_in_system
        self.characteristics = json.dumps(characteristics)
        # Resolu par `create` a partir du prefab quand il y en a un ; sinon
        # tire ici. L'archetype commande l'extraction, il n'est donc jamais
        # simplement recopie de ce que le client annonce.
        self.archetype = archetype or PlanetArchetype.draw()
        self.deposits = self.archetype.roll_deposits()

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def create(cls, system_id, position_in_system, characteristics={}, archetype=None, name=None):
        """
        Allocate a free position.
        ---
        :param position:
        :param archetype: forced archetype, drawn at random when omitted
        :param name: nom affichable du monde, tel que le client l'a baptise
        :return:
        """
        system = System.get(
            id=system_id
        )
        if not Territory.available(system, position_in_system):
            raise ValueError("Position is not available")
        if isinstance(archetype, str):
            archetype = PlanetArchetype.get_by_name(archetype)
        # `planeteScheme` porte le prefab tire par le client, et c'est lui qui
        # fait le lien avec l'archetype : quand il est connu de la table, il
        # tranche. Un client ne peut donc pas annoncer une apparence de monde
        # glace et un archetype de geante gazeuse.
        from_scheme = PlanetArchetype.for_scheme((characteristics or {}).get('planeteScheme'))
        if from_scheme is not None:
            archetype = from_scheme
        territory = Territory(
            system=system,
            position_in_system=position_in_system,
            characteristics=characteristics,
            archetype=archetype,
        )
        # Le nom envoye par le client etait jete : tous les territoires
        # revenaient sans nom, et les listes affichaient du vide.
        territory.name = name
        db.session.add(system)
        db.session.flush()

        for b_type in BuildingType:
            b = Building(
                territory_id=territory.id,
                type=b_type
            )
            db.session.add(b)
            territory.buildings.append(b)

        for d_type in DefenseType:
            d = Defense(
                territory_id=territory.id,
                type=d_type
            )
            territory.defenses.append(d)

        for s_type in ShipType:
            s = Ship(
                territory_id=territory.id,
                type=s_type
            )
            territory.ships.append(s)

        db.session.add(territory)
        db.session.flush()
        return territory

    @classmethod
    def available(cls, system, position_in_system):
        """
        Check position is free
        ---
        :type position: tuple
        :return:
        """
        from app.models.game.system import System
        query = db.session.query(Territory).join(System)\
            .filter(System.id == system.id)\
            .filter(cls.position_in_system == position_in_system)
        return not db.session.query(query.exists()).scalar()

    @classmethod
    def get(cls, id, user=None):
        """
        ---
        :return:
        """
        query = db.session.query(Territory)\
            .filter(cls.id == id)

        if user:
            query = query.filter(cls.user_id == user.id)

        return query.first()

    @classmethod
    def all(cls, user):
        """
        Get all territories matching criteria
        ---
        :param user:
        :return:
        """
        query = db.session.query(Territory).filter()
        return query.all()

    def assign(self, user):
        """
        Assign a territory to a user
        :return:
        """
        self.user_id = user.id

    def update_view(self):
        """
        Update the last viewing of object increasing its resource using a diff between now and previous state
        This will unstack the events system on territory concerned and generate a diff between each events finishes
        ---
        :return:
        """
        logger.info(f"Updating territory {self.id} view")
        if not self.user_id:
            return
        now = datetime.utcnow()
        resource_building = (
            BuildingType.mater_extractor,
            BuildingType.economical_center,
            BuildingType.rafinery
        )
        for event_detail in self.territory_events:
            event = event_detail
            if event.finishing_at <= now:
                # first apply buildings and tech modifications
                # generate diff of resource from previous building level to new finished
                self._apply_modification(event=event)

            elif event.event_type in (PositionalEventType.defense, PositionalEventType.ship):
                # apply all def / ships increase
                duration_for_one = event.extra_args.get("unitaryDuration")
                quantity = event.extra_args.get("quantity")
                last_refresh = event.extra_args.get("lastRefresh", event.created_at)
                if type(last_refresh) == str:
                    last_refresh = datetime.fromisoformat(last_refresh)
                quantity_builded = math.floor(min(quantity, (now - last_refresh).seconds / duration_for_one))
                extra_args = event.extra_args
                # left quantity
                extra_args["quantity"] = quantity - quantity_builded
                extra_args["lastRefresh"] = now.isoformat()
                event.extra_args = extra_args

                if quantity_builded >= 1:
                    # generate diff of resource from previous building level to new finished
                    self._apply_modification(event=event, amount=quantity_builded)
            
            if event.finishing_at <= now:
                # Archive the event if finished
                event.archive()

                # TODO other events ...
        db.session.commit()
        time_elapsed = (datetime.utcnow() - self.updated_at).seconds / 60 / 60  # in hours
        increased_resources = {}

        for r in self.PRODUCED_RESOURCES:
            increased_resources[r] = self.get_hourly_gain(resource_type=r) * time_elapsed
            setattr(self, r.name, (getattr(self, r.name) or 0) + increased_resources[r])

        logger.info(f"Resources increased for territory {self.id}", infos=dict(
            increased_resources=increased_resources,
            time_elapsed=time_elapsed,
            user_id=self.user_id,
        ))
        db.session.commit()

    def _apply_modification(self, event, amount=1):
        resource_building = (
            BuildingType.mater_extractor,
            BuildingType.economical_center,
            BuildingType.rafinery
        )
        if event.event_type == PositionalEventType.building:
            building_type = BuildingType.get_by_name(event.extra_args['name'])
            if building_type in resource_building:
                # There is an event on resource triggered before actual refresh
                time_elapsed = (self.updated_at - event.finishing_at).seconds / 60 / 60  # in hours
                increased_resources = {}

                for r in self.PRODUCED_RESOURCES:
                    increased_resources[r] = self.get_hourly_gain(resource_type=r) * time_elapsed
                    setattr(self, r.name, (getattr(self, r.name) or 0) + increased_resources[r])

            # apply_modification_building
            self.add(type=building_type, amount=amount)
        elif event.event_type in (PositionalEventType.ship, PositionalEventType.defense):
            if event.event_type == PositionalEventType.defense:
                el_type = DefenseType.get_by_name(event.extra_args['name'])
            elif event.event_type == PositionalEventType.ship:
                el_type = ShipType.get_by_name(event.extra_args['name'])
            self.add(type=el_type, amount=amount)

    def get_building(self, building_type):
        """
        ---
        :param building_type:
        :return:
        """
        return next(b for b in self.buildings if b.type == building_type)

    def get_hourly_gain(self, resource_type):
        """
        ---
        :return:
        """
        hourly_gain = 0  # TODO add a base gain on territory without any construction
        buildings = [b for b in self.buildings if resource_type in b.type_of_resource]
        if buildings:
            for b in buildings:
                hourly_gain += b.get_hourly_gain[resource_type]
        if resource_type == ResourceType.energy:
            # Volcanic crusts are worth drilling, icy ones are not.
            hourly_gain *= self.planet_archetype.energy_factor
        if self.user.faction:
            hourly_gain = self.user.faction.apply(
                obj=hourly_gain,
                advantage_scope=FactionAdvantageScope.Resource,
                scope=resource_type.name
            )
        return hourly_gain

    def add(self, type, amount):
        logger.info(f"Adding {amount} of {type} to territory {self.id}", infos=dict(
            type=type,
            amount=amount,
            territory_id=self.id
        ))
        if isinstance(type, ResourceType):
            # Energy is computed from buildings, never stocked.
            if type in ResourceType.stocks():
                setattr(self, type.name, (getattr(self, type.name) or 0) + amount)

        if isinstance(type, BuildingType):
            building = self.get_building(building_type=type)
            if building:
                building.level += amount

        if isinstance(type, DefenseType):
            next(filter(lambda d: d.type, self.defenses)).increment(count=amount)
        if isinstance(type, ShipType):
            next(filter(lambda s: s.type, self.ships)).increment(count=amount)

    def match_prerequisite(self, prerequisites):
        """
        Check if prerequisites are matched or not
        ---
        :param prerequisites: Prerequisites to increase or build something
        :type prerequisites: dict
        :return:
        """
        resources = self.resources
        logger.info(f"Checking prerequisites for territory {self.id}", infos=dict(
            prerequisites=prerequisites,
            resources=resources
        ))
        for k, val in prerequisites.items():
            if val > resources[ResourceType(k)]:
                logger.debug(f"Prerequisite not met: {k} requires {val} but only {resources[ResourceType(k)]} available")
                return False
        return True

    def can_be_increased(self, building_type):
        """
        Check if building can be increase of level
        ---
        :return:
        """
        building = next(b for b in self.buildings if b.type == building_type)
        return self.match_prerequisite(building.cost)

    def increase(self, building_type):
        """
        ---
        :return:
        """
        building = next(b for b in self.buildings if b.type == building_type)
        if building:
            # TODO self.spend(building.cost)
            return PositionalEvent.create(
                territory=self,
                user=self.user,
                duration=building.next_level_duration,
                event_type=PositionalEventType.building,
                extra_args={
                    'name': building.type.name,
                    'level': building.level
                }
            )
            # TODO do it after event finished --> self.add(type=building_type, amount=1)

    def build(self, type, item):
        """
        Build ships or defenses on the territory.
        ---
        """
        shipyard = self.get_building(building_type=BuildingType.shipyard)

        if type == PositionalEventType.ship:
            element = ShipType[item["type"]]
        elif type == PositionalEventType.defense:
            element = DefenseType[item["type"]]
        if not self.match_prerequisite(element.cost):
            raise ValueError(f"Cannot build {item['quantity']} {element.name}. Prerequisites not reached.")

        unitary_duration = element.duration(shipyard=shipyard)
        return PositionalEvent.create(
            territory=self,
            user=self.user,
            duration=unitary_duration * item["quantity"],
            event_type=type,
            extra_args={
                "name": element.name,
                "quantity": item["quantity"],
                "initialQuantity": item["quantity"],
                "unitaryDuration": unitary_duration
            }
        )


    @property
    def energy(self):
        building = next(b for b in self.buildings if b.type == BuildingType.power_station)
        return building.get_hourly_gain[ResourceType.energy] - self.consumption

    @property
    def consumption(self):
        return functools.reduce(lambda acc, x: acc + x, [b.consumption for b in self.buildings])

    @property
    def resources(self):
        """
        Get current resource state on territory
        :return:
        """
        stocks = {r: getattr(self, r.name) or 0 for r in ResourceType.stocks()}
        stocks[ResourceType.energy] = self.energy
        return stocks

    @property
    def galaxy_name(self):
        """
        Galaxie du territoire.
        ---
        Un territoire appartient a un systeme, qui appartient a une galaxie :
        c'est la portee reelle de tout ce qu'un joueur possede.
        """
        return self.system.galaxy_name if self.system else None

    @property
    def planet_archetype(self):
        """Archetype of the world, telluric for rows predating the split."""
        return self.archetype or PlanetArchetype.telluric

    @property
    def deposit_richness(self):
        """Raw richness drawn for this world, 1.0 for rows predating the split."""
        deposits = self.deposits or {}
        if isinstance(deposits, str):  # JSON column written as text
            deposits = json.loads(deposits)
        return {
            material: float(deposits.get(material, 1.0))
            for material in self.planet_archetype.materials
        }

    @property
    def material_yields(self):
        """
        Extraction multiplier per material on this exact world.
        ---
        Archetype ratio x deposit richness. A material the archetype does not
        produce is simply absent: no extractor level can conjure it.
        """
        richness = self.deposit_richness
        return {
            material: ratio * richness.get(material, 1.0)
            for material, ratio in self.planet_archetype.yields.items()
        }

    @property
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'position': self.position_in_system,
            # Remonte a la racine du territoire : les listes cross-systeme
            # (/api/territories) n'ont pas a fouiller le systeme pour savoir
            # de quelle galaxie releve chaque monde.
            'galaxy_name': self.galaxy_name,
            'system': self.system.serialize,
            'buildings': {b.type.name: b for b in self.buildings},
            'characteristics': json.loads(self.characteristics) if self.characteristics else {},
            'archetype': self.planet_archetype.name,
            'archetype_label': self.planet_archetype.label,
            # `deposits` is the raw richness drawn for this world, `yields` the
            # extraction multiplier actually applied (archetype x richness).
            'deposits': self.deposit_richness,
            'yields': self.material_yields,
            'resources': {
                k.name: v for k, v in self.resources.items()
            },
            'updated_at': self.updated_at.isoformat(),
        }
