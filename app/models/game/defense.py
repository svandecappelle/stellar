# Les `requirements.technologies` de ce fichier sont desormais VERIFIES, par
# `Territory.missing_technologies`. Ils ne l'etaient pas : la console les
# affichait, le serveur les ignorait, et le nom `laser` qu'ils reclamaient
# n'existait meme pas dans l'enum des technologies. Les noms ont ete alignes sur
# l'arbre (`atom` -> `atomique`, `chemistry` -> `ogives`, `energy` -> `fission`)
# et c'est ici, et nulle part ailleurs, que se declare ce qu'une piece exige.
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
            "iron": 3000,
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
            "iron": 3000,
            "carbon": 800,
            "credits": 150,
            "energy": 0,
            "population": 2
        },
        "integrity": 2000,
        "requirements": {
            "technologies": {
                "ogives": 2
            }
        }
    }
    LaserArtillery = {
        "name": "LaserArtillery",
        "base_cost": {
            "iron": 2000,
            "cristal": 900,
            "silicium": 600,
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
            "iron": 3000,
            "uranium": 800,
            "silicium": 1000,
            "credits": 1000,
            "energy": 5,
            "population": 2
        },
        "integrity": 12000,
        "requirements": {
            "technologies": {
                "atomique": 8
            }
        }
    }
    Coilgun = {
        "name": "Coilgun",
        "base_cost": {
            "iron": 4000,
            "titanium": 1500,
            "uranium": 600,
            "credits": 2000,
            "energy": 5,
            "population": 3
        },
        "integrity": 20000,
        "requirements": {
            "technologies": {
                "ogives": 6,
                "atomique": 4
            }
        }
    }
    Shield = {
    	"name": "Shield",
    	"base_cost": {
            "iron": 8000,
            "cristal": 3000,
            "uranium": 1500,
            "neutronium": 100,
            "credits": 10000,
            "energy": 100,
            "population": 5
    	},
    	"integrity": 200000,
        "requirements": {
            "technologies": {
                "boucliers": 6
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
        Ajoute des pieces a la batterie.
        ---
        Le compte demande, et non un par appel : la version precedente ignorait
        son argument et incrementait toujours de un, si bien qu'une livraison de
        six pieces en posait une seule.
        """
        self.count += count

    def decrement(self, count):
        """
        Retire des pieces, sans jamais passer sous zero.
        ---
        Le ternaire etait dans le mauvais sens : quand on demandait plus que le
        stock, il retirait tout de meme le montant demande et le compte passait
        negatif.
        """
        self.count -= min(count, self.count)

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