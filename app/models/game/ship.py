import enum
from datetime import datetime

from sqlalchemy import Column, Enum, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base


class ShipType(enum.Enum):
    DefenseSatellite = {
        "name": "DefenseSatellite",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 2000,
        "requirements": {}
    }
    Fighter = {
        "name": "Fighter",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 2000,
        "requirements": {}
    }
    Interceptor = {
        "name": "Interceptor",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 12000,
        "requirements": {}
    }
    Cruiser = {
        "name": "Cruiser",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 27000,
        "requirements": {}
    }
    Frigate = {
        "name": "Frigate",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 60000,
        "requirements": {}
    }
    MotherShip = {
        "name": "MotherShip",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 120000,
        "requirements": {}
    }
    OrbitalStation = {
        "name": "MotherShip",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 10000000,
        "requirements": {}
    }

    def duration(self, factory):
        return self.value["integrity"] / 2500 * (1 + factory.level) * 60

    @property
    def cost(self):
        return self.value["base_cost"]

    @classmethod
    def get_by_name(cls, name):
        return [s for s in ShipType if s.name == name][0]


class Ship(Base):
    """
    Ship class define a territory ship in orbit
    """
    __tablename__ = 'ship_territory'

    id = Column(Integer, primary_key=True)
    type = Column(Enum(ShipType), nullable=False)
    count = Column(Integer, nullable=False, default=0)

    territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territory = relationship("Territory", back_populates="ships")

    def __init__(self, territory_id, type):
        """
        Append a ship on the territory
        """
        self.territory_id = territory_id
        self.type = type
        self.count = 0

    def increment(self, count=1):
        """
        Increase the number of ship into its related territory
        """
        self.count += 1

    def decrement(self, count):
        """
        Decrement the number of ship into its related territory
        """
        self.count -= count if count <= self.count else self.count

    @property
    def serialize(self):
        """
        Serialization method
        ---
        :return:
        """
        return {
            'quantity': self.count,
            'type': self.type.name
        }