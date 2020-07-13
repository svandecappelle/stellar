import enum


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

    def duration(self, level):
        """
        Get the duration of level technology
        :param level:
        :return:
        """
        return TechnologyEquations.get(tech_type=self, equation_type=EquationType.time)(level)

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
        TechnologyType.computer: lambda x: 5 * pow(3, x)
    }

    PRICE_EQUATIONS = {
        TechnologyType.computer: lambda x, base: base * pow(2, (x-1))
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

