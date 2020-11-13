import enum

from app.models.game.community.faction import FactionAdvantageScope

class EquationType(enum.Enum):
    time = "time"
    price = "price"


class TechnologyType(enum.Enum):
    computer = {
        "name": "computer",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    optical = {
        "name": "optical",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    chemistry = {
        "name": "chemistry",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    alliage = {
        "name": "alliage",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    energy = {
        "name": "energy",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    distorsion = {
        "name": "distorsion",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }
    atom = {
        "name": "atom",
        "base_cost": {
            "mater": 400,
            "credits": 600,
            "energy": 0,
            "population": 0
        }
    }

    def __init__(self, value):
        # self.name = value['name']
        self.base_cost = value['base_cost']

    @classmethod
    def get_by_name(cls, name):
        for t in cls:
            if name == t.name:
                return t

    def duration(self, level, user):
        """
        Get the duration of level technology
        :param level:
        :return:
        """
        time = TechnologyEquations.get(
            tech_type=self,
            equation_type=EquationType.time,
        )(level)
        if user.faction:
            time = user.faction.apply(
                obj=time,
                advantage_scope=FactionAdvantageScope.Technologies
            )
        return time

    def price(self, level):
        """
        ---
        :param level:
        :return:
        """
        return {
            "mater": TechnologyEquations.get(
                tech_type=self, equation_type=EquationType.price
            )(level, self.base_cost['mater']),
            "credits": TechnologyEquations.get(
                tech_type=self, equation_type=EquationType.price
            )(level, self.base_cost['credits']),
            "energy": TechnologyEquations.get(
                tech_type=self, equation_type=EquationType.price
            )(level, self.base_cost['energy']),
            "population": TechnologyEquations.get(
                tech_type=self, equation_type=EquationType.price
            )(level, self.base_cost['population'])
        }


class TechnologyEquations:

    TIME_EQUATIONS = {
        TechnologyType.computer: lambda x: 5 * pow(3, x),
        TechnologyType.optical: lambda x: 5 * pow(3, x),
        TechnologyType.chemistry: lambda x: 5 * pow(3, x),
        TechnologyType.alliage: lambda x: 5 * pow(3, x),
        TechnologyType.energy: lambda x: 5 * pow(3, x),
        TechnologyType.distorsion: lambda x: 5 * pow(3, x),
        TechnologyType.atom: lambda x: 5 * pow(3, x)
    }

    PRICE_EQUATIONS = {
        TechnologyType.computer: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.optical: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.chemistry: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.alliage: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.energy: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.distorsion: lambda x, base: base * pow(2, (x-1)),
        TechnologyType.atom: lambda x, base: base * pow(2, (x-1))
    }

    @classmethod
    def get(cls, tech_type, equation_type):
        """
        ---
        :param equation_type:
        :param tech_type:
        :return:
        """
        if equation_type == EquationType.time:
            return cls.TIME_EQUATIONS.get(tech_type)
        if equation_type == EquationType.price:
            return cls.PRICE_EQUATIONS.get(tech_type)