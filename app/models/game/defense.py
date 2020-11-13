import enum
from datetime import datetime

from sqlalchemy import Column, Enum, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base


class DefenseType(enum.Enum):
    FlackCannon = {
        "name": "FlackCannon",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 2000,
        "requirements": {}
    }
    MissileBattery = {
        "name": "MissileBattery",
        "base_cost": {
            "mater": 3500,
            "credits": 150,
            "energy": 0,
            "population": 2
        },
        "integrity": 2000,
        "requirements": {}
    }
    LaserArtillery = {
        "name": "LaserArtillery",
        "base_cost": {
            "mater": 2400,
            "credits": 600,
            "energy": 1,
            "population": 1
        },
        "integrity": 8000,
        "requirements": {
        	"technologies": {
        		"laser": 5
        	}
        }
    }
    IonArtillery = {
        "name": "IonArtillery",
        "base_cost": {
            "mater": 3500,
            "credits": 1000,
            "energy": 5,
            "population": 2
        },
        "integrity": 12000,
        "requirements": {
        	"technologies": {
        		"atom": 8
        	}
        }
    }
    Coilgun = {
        "name": "Coilgun",
        "base_cost": {
            "mater": 5000,
            "credits": 2000,
            "energy": 5,
            "population": 3
        },
        "integrity": 20000,
        "requirements": {
        	"technologies": {
        		"atom": 8,
        		"chemistry": 6
        	}
        }
    }
    Shield = {
    	"name": "Shield",
    	"base_cost": {
    		"mater": 10000,
    		"credits": 10000,
    		"energy": 100,
    		"population": 5
    	},
    	"integrity": 200000,
        "requirements": {
        	"technologies": {
        		"energy": 8
        	}
        }
    }

    def duration(self, shipyard):
        return self.value["integrity"] / 2500 * (1 + shipyard.level) * 60

    @property
    def cost(self):
        return self.value["base_cost"]

    @classmethod
    def get_by_name(cls, name):
        return [d for d in DefenseType if d.name == name][0]


class Defense(Base):
    """
    Ship class define a territory ship in orbit
    """
    __tablename__ = 'defense_territory'

    id = Column(Integer, primary_key=True)
    type = Column(Enum(DefenseType), nullable=False)
    count = Column(Integer, nullable=False, default=0)

    territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territory = relationship("Territory", back_populates="defenses")

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