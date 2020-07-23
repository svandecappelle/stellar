from datetime import datetime
import enum

from app.models.base import Base

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship


class BuildingType(enum.Enum):
    academy = {
        'cost': {
            'mater': lambda n: 200 * pow(2, n - 1),
            'credit': lambda n: 400 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    economical_center = {
        'cost': {
            'mater': lambda n: 48 * pow(1.6, n - 1),
            'credit': lambda n: 24 * pow(1.6, n - 1),
            'energy': lambda n: 10 * n * pow(1.1, n)
        },
        'gain': {
            'credits': lambda n: 30 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    factory = {
        'cost': {
            'mater': lambda n: 400 * pow(2, n - 1),
            'credit': lambda n: 120 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    mater_extractor = {
        'cost': {
            'mater': lambda n: 60 * pow(1.5, n - 1),
            'credit': lambda n: 15 * pow(1.5, n - 1),
            'energy': lambda n: 10 * n * pow(1.1, n)
        },
        'gain': {
            'mater': lambda n: 30 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    power_station = {
        'cost': {
            'mater': lambda n: 75 * pow(1.6, n - 1),
            'credit': lambda n: 30 * pow(1.6, n - 1),
        },
        'gain': {
            'energy': lambda n: 13 + 20 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    rafinery = {
        'cost': {
            'mater': lambda n: 75 * pow(1.6, n - 1),
            'credit': lambda n: 30 * pow(1.6, n - 1),
            'energy': lambda n: 20 * n * pow(1.1, n)
        },
        'gain': {
            'tritium': lambda n: 10 * n * pow(1.1, n) * (-0.002 * 40 + 1.28)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    shipyard = {
        'cost': {
            'mater': lambda n: 200 * pow(2, n - 1),
            'credit': lambda n: 400 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x)
    }

    def __str__(self):
        return self.name

    @classmethod
    def get_by_name(cls, name):
        return [b for b in BuildingType if b.name == name][0]

    def get_hourly_gain(self, level):
        """
        Get gain hourly
        ---
        :param level:
        :return:
        """
        from app.models.game.territory import ResourceType
        return {t: self.get_resource_gain(resource_type=t, level=level) for t in ResourceType}

    def get_resource_cost(self, resource_type, level):
        """
        ---
        :return:
        """
        resource_cost_func = self.value['cost'].get(resource_type.name, None)
        return resource_cost_func(level) if resource_cost_func is not None else 0

    def get_resource_gain(self, resource_type, level):
        """
        ---
        :return:
        """
        resource_cost_func = self.value['gain'].get(resource_type.name, None)
        return resource_cost_func(level) if resource_cost_func is not None else 0

    def get_cost(self, level):
        """
        Get level cost of building
        ---
        :param level:
        :return:
        """
        from app.models.game.territory import ResourceType
        return {t: self.get_resource_cost(resource_type=t, level=level) for t in ResourceType}

    @property
    def type_of_resource(self):
        from app.models.game.territory import ResourceType
        return [ResourceType(g) for g in self.value.get('gain', {}).keys()]

    def duration(self, level):
        """
        Get the duration of level technology
        :param level:
        :return:
        """
        return self.value.get('time')(level)


class Building(Base):

    __tablename__ = 'territory_buildings'

    id = Column(Integer, primary_key=True)
    type = Column(Enum(BuildingType), nullable=False)
    level = Column(Integer, nullable=False)

    territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territory = relationship("Territory", back_populates="buildings")

    def __init__(self, type, territory_id, level=0):
        self.type = type
        self.territory_id=territory_id
        self.level = level

    @property
    def get_hourly_gain(self):
        """
        Get hourly gain of a resource building
        ---
        :return:
        """
        return self.type.get_hourly_gain(level=self.level)

    @property
    def type_of_resource(self):
        return self.type.type_of_resource

    @property
    def cost(self):
        return self.type.get_cost(level=self.level + 1)

    @property
    def consumption(self):
        from app.models.game.territory import ResourceType
        return self.type.get_cost(level=self.level)[ResourceType.energy]

    @property
    def next_level_duration(self):
        """
        ---
        :return:
        """
        current_factory_level = self.territory.get_building(building_type=BuildingType.factory).level
        return self.type.duration(level=self.level) * (1 / (current_factory_level + 1))

    @property
    def serialize(self):
        """
        Serialization method
        ---
        :return:
        """
        return {
            'level': self.level,
            'duration': self.next_level_duration
        }