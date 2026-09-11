import enum
import json
from datetime import datetime

from app.models.base import Base
from app.models.game.settings import GalaxySettings

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship


class BuildingType(enum.Enum):
    # NOTE the cost keys must match `ResourceType` member names exactly:
    # they used to read 'credit' where the enum says 'credits', so every
    # building was silently free of credits.
    # Le seul batiment qui ne rendait rien : il coutait cher et ne servait a
    # rien d'autre qu'a exister. Il produit desormais les Donnees, la ressource
    # que consomme l'arbre technologique — et ses niveaux cumules sur l'empire
    # ouvrent les emplacements de recherche menes de front (voir
    # `Technology.slots`). L'academie devient ce qu'elle aurait toujours du
    # etre : le batiment de la recherche.
    academy = {
        'cost': {
            'silicium': lambda n: 200 * pow(2, n - 1),
            'cristal': lambda n: 120 * pow(2, n - 1),
            'credits': lambda n: 400 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'gain': {
            'research': lambda n: 8 + 12 * n * pow(1.1, n)
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
    # La ferme est le seul producteur de nourriture. Ce qu'elle rend depend du
    # monde sur lequel elle est posee : voir `PlanetArchetype.habitability`, applique
    # dans `Building.get_hourly_gain`. Comme la centrale, elle donne un fond de
    # recolte des le niveau 0 — un monde habite mange avant de savoir construire.
    farm = {
        'cost': {
            'iron': lambda n: 50 * pow(1.5, n - 1),
            'carbon': lambda n: 60 * pow(1.5, n - 1),
            'credits': lambda n: 20 * pow(1.5, n - 1),
            'energy': lambda n: 8 * n * pow(1.1, n)
        },
        'gain': {
            'food': lambda n: 15 + 25 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x)
    }
    # Deux batiments seulement sont derriere l'arbre, et ce sont les deux qui
    # accelerent le reste : l'usine pour les chantiers, le chantier naval pour
    # les coques. Les autres restent libres — une colonie doit pouvoir manger,
    # s'eclairer et chercher sans avoir rien cherche, sans quoi le premier tour
    # de jeu n'a pas d'issue.
    factory = {
        'cost': {
            'iron': lambda n: 400 * pow(2, n - 1),
            'titanium': lambda n: 150 * pow(2, n - 1),
            'credits': lambda n: 120 * pow(2, n - 1),
            'tritium': lambda n: 200 * pow(2, n - 1)
        },
        'time': lambda x: 5 * pow(3, x),
        'requirements': {
            'technologies': {
                'chantiers': 2
            }
        }
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
    # Le depot : ce qui permet a une ligne de commerce d'exister, et ce qui
    # fixe son debit. Une ligne demande un depot AUX DEUX BOUTS, et coule au
    # rythme du plus faible des deux.
    #
    # Sans prerequis technologique, et c'est deliberé : une ligne est la seule
    # reponse a l'isolement, et l'isolement coute de la stabilite des la
    # premiere heure. Mettre le depot derriere l'arbre reviendrait a punir un
    # joueur pour une recherche qu'il n'a pas encore pu faire.
    depot = {
        'cost': {
            'iron': lambda n: 120 * pow(1.7, n - 1),
            'silicium': lambda n: 80 * pow(1.7, n - 1),
            'credits': lambda n: 60 * pow(1.7, n - 1),
            'energy': lambda n: 6 * n * pow(1.1, n)
        },
        # Aucun `gain` : un depot ne produit rien. Ce qu'il donne est un debit,
        # lu par la ligne de commerce — voir `app/models/game/trade.py`.
        'time': lambda x: 5 * pow(3, x)
    }
    # Le craqueur : le seul batiment du jeu dont l'ENTREE est une ressource.
    #
    # Il casse l'hydrogene en tritium. Jusqu'ici l'hydrogene n'etait consomme
    # que par trois technologies, tres haut dans l'arbre — et la geante gazeuse,
    # qui en est de loin la meilleure source, produisait donc une ressource sans
    # debouche. Le tritium, lui, verrouille l'academie, l'usine et le chantier
    # naval : c'est ce qui fait d'une plateforme sur geante un accelerateur
    # industriel, et non un decor.
    #
    # Le rendement vit dans `Territory._run_cracking`, pas dans un `gain` : une
    # production qui consomme ne se decrit pas par une courbe seule.
    gas_cracker = {
        'cost': {
            'iron': lambda n: 300 * pow(1.8, n - 1),
            'titanium': lambda n: 150 * pow(1.8, n - 1),
            'credits': lambda n: 250 * pow(1.8, n - 1),
            'energy': lambda n: 25 * n * pow(1.1, n)
        },
        'time': lambda x: 5 * pow(3, x),
        'requirements': {
            'technologies': {
                'raffinage': 2
            }
        }
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
        # Comme la centrale et la ferme, un fond au niveau 0 puis une courbe qui
        # part de la : `max(10, 10 * n * ...)` faisait rendre 10 au niveau 0 et
        # 13.2 au niveau 1, soit quarante-cinq heures pour amortir le premier
        # palier -- le pire investissement du jeu, et un passage oblige puisque
        # le tritium verrouille l'academie, l'usine et le chantier naval.
        #
        # Ce que rend vraiment la raffinerie depend de l'eau du monde : le
        # multiplicateur est applique dans `Building.get_hourly_gain`, la ou le
        # territoire est connu.
        'gain': {
            'tritium': lambda n: 10 + 12 * n * pow(1.1, n)
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
        'time': lambda x: 5 * pow(3, x),
        'requirements': {
            'technologies': {
                'alliages': 3
            }
        }
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

        Les reglages de la galaxie sont appliques ici, et nulle part ailleurs :
        c'est cette valeur que le territoire additionne, que l'API serialise et
        que le client de jeu affiche. Plus haut, la production creditee et la
        production annoncee auraient fini par differer.
        """
        from app.models.game.territory import ResourceType

        galaxy_name = self.territory.galaxy_name if self.territory else None
        gains = self.type.get_hourly_gain(level=self.level)

        if self.type.is_extractor:
            extraction = self.type.get_extraction(level=self.level)
            extraction *= GalaxySettings.value(galaxy_name, 'extraction_multiplier')
            for material, factor in self.territory.material_yields.items():
                gains[ResourceType(material)] = extraction * factor

        overall = GalaxySettings.value(galaxy_name, 'resource_gain_multiplier')
        if overall != 1.0:
            gains = {resource: gain * overall for resource, gain in gains.items()}

        # La recolte depend du monde : une geante gazeuse ne nourrit personne,
        # quel que soit le niveau de la ferme.
        if self.territory is not None and gains.get(ResourceType.food):
            gains[ResourceType.food] *= self.territory.planet_archetype.habitability_factor

        # Le tritium se tire de l'eau du monde. C'est le seul terme qui fasse
        # varier une raffinerie d'un endroit a l'autre : sans lui elle rendait
        # la meme chose sur un oceanique et sur un caillou sec.
        if self.territory is not None and gains.get(ResourceType.tritium):
            gains[ResourceType.tritium] *= self.territory.planet_archetype.water_factor

        # Un monde qui gronde produit moins. Deux exceptions, et elles ont la
        # meme raison : sans elles, une famine serait sans retour.
        #
        #   · la nourriture, parce qu'elle est la seule sortie d'une famine ;
        #   · l'energie, parce qu'elle n'est pas un stock mais un plafond. La
        #     rogner retirerait au joueur des batiments qu'il a deja payes, et
        #     l'empecherait de monter la ferme qui le sauverait.
        spared = (ResourceType.food, ResourceType.energy)
        unrest = self.territory.stability_factor if self.territory else 1.0
        if unrest != 1.0:
            gains = {
                resource: gain if resource in spared else gain * unrest
                for resource, gain in gains.items()
            }

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
        """
        Cout du niveau suivant, tel que la galaxie le pratique.
        ---
        Un seul endroit, lu par la verification de prerequis comme par la
        serialisation : le joueur paie ce qui lui est annonce.
        """
        from app.models.game.modifiers import NO_MODIFIERS, ModifierScope

        galaxy_name = self.territory.galaxy_name if self.territory else None
        multiplier = GalaxySettings.value(galaxy_name, 'building_cost_multiplier')
        costs = self.type.get_cost(level=self.level + 1)

        if multiplier != 1.0:
            costs = {resource: amount * multiplier for resource, amount in costs.items()}

        # `Metallurgie appliquee` et `Automatisation` agissent ici : sur le cout
        # annonce comme sur le cout paye, puisque c'est la meme valeur.
        modifiers = self.territory.modifiers if self.territory else NO_MODIFIERS
        return modifiers.apply_cost(costs, scope=ModifierScope.Buildings)

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
        from app.models.game.modifiers import NO_MODIFIERS, ModifierScope

        current_factory_level = self.territory.get_building(building_type=BuildingType.factory).level
        duration = self.type.duration(level=self.level) * (1 / (current_factory_level + 1))

        galaxy_name = self.territory.galaxy_name if self.territory else None
        duration = duration / GalaxySettings.value(galaxy_name, 'build_time_divider')

        # `Chantiers modulaires` agit ici, apres le reglage de galaxie : les
        # deux se multiplient, aucun n'annule l'autre.
        modifiers = self.territory.modifiers if self.territory else NO_MODIFIERS
        return modifiers.shorten(duration, scope=ModifierScope.Buildings)

    @property
    def serialize(self):
        """
        Serialization method
        ---
        :return:
        """
        return {
            'level': self.level,
            'requirements': self.type.value.get('requirements', {}),
            'duration': self.next_level_duration,
            'gain': { str(k): v for k, v in self.get_hourly_gain.items() },
            'cost': { str(k): v for k, v in self.cost.items() },  # FIXME avoid json.dumps in model
        }