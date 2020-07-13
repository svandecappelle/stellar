from datetime import datetime
import enum

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType, Building
from app.models.game.event import PositionalEventType


class ResourceType(enum.Enum):
    mater = "mater"
    credit = "credit"
    energy = "energy"
    population = "population"
    combustible = "combustible"


class Territory(Base):
    __tablename__ = 'territory'

    id = Column(Integer, primary_key=True)

    position_in_system = Column(Integer, nullable=False)
    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    name = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    mater = Column(Integer, default=100, nullable=False)
    credits = Column(Integer, default=100, nullable=False)
    energy = Column(Integer, default=0, nullable=False)
    population = Column(Integer, default=100, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buildings = relationship("Building", back_populates="territory")

    system = relationship("System", back_populates="territories")
    territory_events = relationship("PositionalEventDetail", back_populates="territory")
    user = relationship("User", back_populates="territories")

    def __init__(self, sector_id, system, position_in_system):
        self.sector_id = sector_id
        self.system_id = system.id
        self.position_in_system = position_in_system

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def new(cls, position=None):
        """
        Allocate a free position.
        ---
        :param position:
        :return:
        """
        from app.models.game.system import System
        if not position:
            position = cls.optimized_available_position()
        if not Territory.available(position):
            raise ValueError("Position is not available")
        system = System.get_or_create(
            sector_id=position[0],
            position=position[1],
        )
        territory = Territory(
            sector_id=position[0],
            system=system,
            position_in_system=position[2]
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

        db.session.add(territory)
        db.session.flush()
        return territory

    @classmethod
    def available(cls, position):
        """
        Check position is free
        ---
        :type position: tuple
        :return:
        """
        from app.models.game.system import System
        query = db.session.query(Territory).join(System)\
            .filter(System.id == position[0])\
            .filter(System.position == position[1])\
            .filter(cls.position_in_system == position[2])
        return not db.session.query(query.exists()).scalar()

    @classmethod
    def optimized_available_position(cls):
        """
        ---
        :return:
        """
        from app.models.game.system import System
        query = db.session.query(
            func.max(System.sector_id),
            func.min(System.sector_id),
            func.avg(System.sector_id),

            func.max(System.position),
            func.min(System.position),
            func.avg(System.position)
        ).join(Territory)

        max_sector, min_sector, avg_sector, max_system, min_system, avg_system = query.one()
        if max_sector is None:
            # TODO Generate it with random.
            # Not any territory: place it approximately at center of galaxy
            return (5, 500, 6)

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
        resource_building = (
            "mater_extractor",
            "space_port",
            "power_station"
        )
        for event in self.territory_events:
            if event.finishing_at >= datetime.utcnow():
                # generate diff of resource
                if event.event_type == PositionalEventType.building and event.extra_args['building'] in resource_building:
                    # There is an event on resource triggered before actual refresh
                    self.mater = self.get_hourly_gain(resource_type=ResourceType.mater) * (self.updated_at - event.finishing_at).hours

                # apply_modification_building

                # TODO other events ...

    def get_hourly_gain(self, resource_type):
        """

        :return:
        """
        building = filter(self.buildings, lambda b: b.type == resource_type)
        return building.get_hourly_gain()

    def add(self, type, amount):
        if isinstance(type, ResourceType):
            if type == ResourceType.mater:
                self.mater += amount

            if type == ResourceType.credit:
                self.credits += amount

        if isinstance(type, BuildingType):
            building = next(b for b in self.buildings if b.type == type)
            if building:
                building.level += amount

    @property
    def energy(self):
        building = next(b for b in self.buildings if b.type == BuildingType.power_station)
        return building.get_hourly_gain[ResourceType.energy.name]

    @property
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'position': self.position_in_system,
            'system': self.system.serialize
        }
