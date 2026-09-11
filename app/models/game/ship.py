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
            "iron": 2500,
            "silicium": 500,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 2000,
        "requirements": {
            "technologies": {
                "ciblage": 1
            }
        }
    }
    Fighter = {
        "name": "Fighter",
        "base_cost": {
            "iron": 2000,
            "titanium": 800,
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
            "iron": 2500,
            "titanium": 1200,
            "silicium": 400,
            "credits": 80,
            "energy": 0,
            "population": 1
        },
        "integrity": 12000,
        "requirements": {
            "technologies": {
                "coques_renforcees": 1
            }
        }
    }
    Cruiser = {
        "name": "Cruiser",
        "base_cost": {
            "iron": 6000,
            "titanium": 3000,
            "silicium": 800,
            "credits": 200,
            "energy": 0,
            "population": 3
        },
        "integrity": 27000,
        "requirements": {
            "technologies": {
                "blindage_composite": 1
            }
        }
    }
    Frigate = {
        "name": "Frigate",
        "base_cost": {
            "iron": 12000,
            "titanium": 6000,
            "silicium": 1500,
            "cristal": 400,
            "credits": 500,
            "energy": 0,
            "population": 5
        },
        "integrity": 60000,
        "requirements": {
            "technologies": {
                "artillerie_lourde": 1
            }
        }
    }
    MotherShip = {
        "name": "MotherShip",
        "base_cost": {
            "iron": 40000,
            "titanium": 20000,
            "silicium": 5000,
            "cristal": 2000,
            "neutronium": 200,
            "credits": 3000,
            "energy": 0,
            "population": 20
        },
        "integrity": 120000,
        # Le vaisseau-mere et la station etaient constructibles des la premiere
        # heure : les deux coques les plus lourdes du jeu ne demandaient rien.
        # C'est le deblocage que la percee `Antimatiere` porte dans l'arbre.
        "requirements": {
            "technologies": {
                "antimatiere": 1,
                "titan": 1
            }
        }
    }
    OrbitalStation = {
        "name": "OrbitalStation",
        "base_cost": {
            "iron": 60000,
            "titanium": 25000,
            "silicium": 6000,
            "neutronium": 500,
            "credits": 5000,
            "energy": 0,
            "population": 25
        },
        "integrity": 10000000,
        "requirements": {
            "technologies": {
                "antimatiere": 1,
                "bouclier_planetaire": 1
            }
        }
    }
    # Les deux coques de l'expansion. Elles se CONSOMMENT a l'usage : c'est la
    # seule regle neuve du modele de flotte, et elle vaut pour les deux.
    #
    # Le vaisseau de colonisation coute des habitants, et beaucoup : quarante
    # sur les cent d'un monde de depart. L'expansion se paie en gens, pas
    # seulement en metal, sans quoi rien n'empecherait d'essaimer sans fin.
    ColonyShip = {
        "name": "ColonyShip",
        "base_cost": {
            "iron": 2400,
            "silicium": 900,
            "credits": 300,
            "energy": 0,
            "population": 40
        },
        "integrity": 4000,
        "requirements": {
            "technologies": {
                "poussee_chimique": 1
            }
        }
    }
    # Le cargo ouvre une ligne de commerce, et s'y consomme : il fait le
    # premier voyage, la route reste. C'est ce qui fait qu'une ligne se
    # construit au lieu de se decreter, et ce qui donne du poids a la
    # geographie — la distance est un cout en temps, pas un mur.
    Freighter = {
        "name": "Freighter",
        "base_cost": {
            "iron": 3200,
            "titanium": 600,
            "silicium": 700,
            "credits": 400,
            "energy": 0,
            "population": 8
        },
        "integrity": 5000,
        "requirements": {
            "technologies": {
                "convoyeurs": 1
            }
        }
    }
    # La plateforme se pose sur ce qui ne se colonise pas. Elle ne demande pas
    # la technologie du corps vise — geante, asteroide ou anomalie exigent
    # chacun la leur, verifiee a l'arrimage : une coque qui les cumulerait
    # interdirait de batir la plateforme avant de savoir tout arraisonner.
    ExtractionPlatform = {
        "name": "ExtractionPlatform",
        "base_cost": {
            "iron": 9000,
            "titanium": 3000,
            "silicium": 1500,
            "credits": 800,
            "energy": 0,
            "population": 5
        },
        "integrity": 8000,
        "requirements": {
            "technologies": {
                "moulage_sous_vide": 1
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
        return [s for s in ShipType if s.name == name][0]


class Ship(Base):
    """
    Un lot de vaisseaux d'un meme type au sein d'une flotte.

    Le stock ne pend plus au territoire : un vaisseau assemble quitte la planete
    pour l'espace du systeme, ou il appartient a une flotte. Voir
    `app/models/game/fleet.py` pour la regle d'affectation a la sortie du
    chantier, et pour la position — elle est portee par la flotte, seule chose
    qui manoeuvre.
    """
    __tablename__ = 'ship'

    id = Column(Integer, primary_key=True)
    type = Column(Enum(ShipType), nullable=False)
    count = Column(Integer, nullable=False, default=0)

    fleet_id = Column(Integer, ForeignKey("fleet.id"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    fleet = relationship("Fleet", back_populates="ships")

    def __init__(self, fleet_id, type, count=0):
        self.fleet_id = fleet_id
        self.type = type
        self.count = count

    def increment(self, count=1):
        """
        Ajoute des vaisseaux au lot.
        ---
        Le compte demande, et non un par appel : la version precedente ignorait
        son argument et incrementait toujours de un, si bien qu'une livraison de
        six vaisseaux en posait un seul.
        """
        self.count += count

    def decrement(self, count):
        """
        Retire des vaisseaux du lot, sans jamais passer sous zero.
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
