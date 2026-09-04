import enum
import json
from datetime import datetime

from app.models.base import Base

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship


class BuildingType(enum.Enum):
    # NOTE the cost keys must match `ResourceType` member names exactly:
    # they used to read 'credit' where the enum says 'credits', so every
    # building was silently free of credits.
    academy = {
        'cost': {
            'silicium': lambda n: 200 * pow(2, n - 1),
            'cristal': lambda n: 120 * pow(2, n - 1),
            'credits': lambda n: 400 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    economical_center = {
        'cost': {
            'iron': lambda n: 48 * pow(1.6, n - 1),
            'silicium': lambda n: 30 * pow(1.6, n - 1),
            'credits': lambda n: 24 * pow(1.6, n - 1),
            'energy': lambda n: 10 * n * pow(1.1, n)
        },
        'gain': {
            'credits': lambda n: max(3, 30 * n * pow(1.1, n))
        },
        'time': lambda x: 5 * pow(3, x)
    }
    factory = {
        'cost': {
            'iron': lambda n: 400 * pow(2, n - 1),
            'titanium': lambda n: 150 * pow(2, n - 1),
            'credits': lambda n: 120 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    # The one extractor. What it actually pulls out of the ground is decided
    # by the planet archetype, not by the building: see `Building.get_hourly_gain`.
    mater_extractor = {
        'cost': {
            'iron': lambda n: 60 * pow(1.5, n - 1),
            'carbon': lambda n: 30 * pow(1.5, n - 1),
            'credits': lambda n: 15 * pow(1.5, n - 1),
            'energy': lambda n: 10 * n * pow(1.1, n)
        },
        'extraction': lambda n: max(30, 30 * n * pow(1.1, n)),
        'time': lambda x: 5 * pow(3, x)
    }
    power_station = {
        'cost': {
            'iron': lambda n: 75 * pow(1.6, n - 1),
            'carbon': lambda n: 40 * pow(1.6, n - 1),
            'credits': lambda n: 30 * pow(1.6, n - 1),
        },
        'gain': {
            'energy': lambda n: 13 + 20 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    rafinery = {
        'cost': {
            'iron': lambda n: 75 * pow(1.6, n - 1),
            'silicium': lambda n: 40 * pow(1.6, n - 1),
            'credits': lambda n: 30 * pow(1.6, n - 1),
            'energy': lambda n: 20 * n * pow(1.1, n)
        },
        'gain': {
            'tritium': lambda n: max(10, 10 * n * pow(1.1, n) * (-0.002 * 40 + 1.28))
        },
        'time': lambda x: 5 * pow(3, x)
    }
    shipyard = {
        'cost': {
            'iron': lambda n: 200 * pow(2, n - 1),
            'titanium': lambda n: 200 * pow(2, n - 1),
            'credits': lambda n: 400 * pow(2, n - 1),
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
        resource_cost_func = self.value.get('gain', {}).get(resource_type.name, None)
        if resource_cost_func is None:
            return 0
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

    @property
    def is_extractor(self):
        return 'extraction' in self.value

    def get_extraction(self, level):
        """
        Base extraction rate at that level, before the planet has its say.
        ---
        :return: a scalar, not a per-resource mapping: which materials this
                 becomes depends on the territory the building stands on.
        """
        extraction_func = self.value.get('extraction')
        return extraction_func(level) if extraction_func is not None else 0

    def duration(self, level):
        """
        Get the duration of level technology
        ---
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
        self.territory_id = territory_id
        self.level = level

    @property
    def get_hourly_gain(self):
        """
        Get hourly gain of a resource building
        ---
        An extractor produces whatever its planet holds: the base rate is split
        across the archetype materials, weighted by the local deposits.
        """
        from app.models.game.territory import ResourceType

        gains = self.type.get_hourly_gain(level=self.level)
        if self.type.is_extractor:
            extraction = self.type.get_extraction(level=self.level)
            for material, factor in self.territory.material_yields.items():
                gains[ResourceType(material)] = extraction * factor
        return gains

    @property
    def type_of_resource(self):
        """
        Resources this building feeds on this territory.
        ---
        Territory-aware on purpose: the same extractor yields titanium on an
        asteroid and nothing but hydrogen on a gas giant.
        """
        from app.models.game.territory import ResourceType

        types = list(self.type.type_of_resource)
        if self.type.is_extractor:
            types += [ResourceType(m) for m in self.territory.material_yields.keys()]
        return types

    @property
    def cost(self):
        return self.type.get_cost(level=self.level + 1)

    @property
    def consumption(self):
        from app.models.game.territory import ResourceType
        return self.type.get_cost(level=self.level).get(ResourceType.energy, 0)

    @property
    def next_level_duration(self):
        """
        Get the next level building duration
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
            'duration': self.next_level_duration,
            'gain': { str(k): v for k, v in self.get_hourly_gain.items() },
            'cost': { str(k): v for k, v in self.cost.items() },  # FIXME avoid json.dumps in model
        }