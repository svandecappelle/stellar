import functools
from datetime import datetime
import enum
import math

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType, Building
from app.models.game.community.faction import FactionAdvantageScope
from app.models.game.defense import Defense, DefenseType
from app.models.game.event import PositionalEventType, PositionalEvent
from app.models.game.ship import Ship, ShipType
from app.models.game.system import System


class ResourceType(enum.Enum):
    mater = "mater"
    credits = "credits"
    energy = "energy"
    population = "population"
    tritium = "tritium"


class Territory(Base):
    __tablename__ = 'territory'

    id = Column(Integer, primary_key=True)

    position_in_system = Column(Integer, nullable=False)
    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    name = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    mater = Column(Integer, default=10000, nullable=False)
    credits = Column(Integer, default=8000, nullable=False)
    tritium = Column(Integer, default=100, nullable=False)
    population = Column(Integer, default=100, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buildings = relationship("Building", back_populates="territory")
    ships = relationship("Ship", back_populates="territory")
    defenses = relationship("Defense", back_populates="territory")

    system = relationship("System", back_populates="territories")
    territory_events = relationship("PositionalEventDetail", back_populates="territory")
    user = relationship("User", back_populates="territories")

    def __init__(self, system, position_in_system):
        self.system_id = system.id
        self.position_in_system = position_in_system

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def new(cls, galaxy, system_id, position_in_system):
        """
        Allocate a free position.
        ---
        :param position:
        :return:
        """
        system = System.get(
            id=system_id
        )
        if not Territory.available(system, position_in_system):
            raise ValueError("Position is not available")
        territory = Territory(
            system=system,
            position_in_system=position_in_system
        )
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
        now = datetime.utcnow()
        resource_building = (
            BuildingType.mater_extractor,
            BuildingType.economical_center,
            BuildingType.rafinery
        )
        for event_detail in self.territory_events:
            event = event_detail.event
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

        for r in (ResourceType.mater, ResourceType.credits, ResourceType.tritium):
            increased_resources[r] = self.get_hourly_gain(resource_type=r) * time_elapsed

        self.mater += increased_resources[ResourceType.mater]
        self.credits += increased_resources[ResourceType.credits]
        self.tritium += increased_resources[ResourceType.tritium]
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

                for r in (ResourceType.mater, ResourceType.credits, ResourceType.tritium):
                    increased_resources[r] = self.get_hourly_gain(resource_type=r) * time_elapsed

                self.mater += increased_resources[ResourceType.mater]
                self.credits += increased_resources[ResourceType.credits]
                self.tritium += increased_resources[ResourceType.tritium]

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
        if self.user.faction:
            hourly_gain = self.user.faction.apply(
                obj=hourly_gain,
                advantage_scope=FactionAdvantageScope.Resource,
                scope=resource_type.name
            )
        return hourly_gain

    def add(self, type, amount):
        if isinstance(type, ResourceType):
            if type == ResourceType.mater:
                self.mater += amount
            if type == ResourceType.credits:
                self.credits += amount
            if type == ResourceType.tritium:
                self.tritium += amount
            if type == ResourceType.population:
                self.population += amount

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
        for k, val in prerequisites.items():
            resources = self.resources
            if val > resources[ResourceType(k)]:
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
        return {
            ResourceType.mater: self.mater,
            ResourceType.credits: self.credits,
            ResourceType.energy: self.energy,
            ResourceType.population: self.population,
            ResourceType.tritium: self.tritium
        }

    @property
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'position': self.position_in_system,
            'system': self.system.serialize,
            'buildings': {b.type.name: b for b in self.buildings}
        }
