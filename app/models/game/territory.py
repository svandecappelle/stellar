import functools
import json
from datetime import datetime
import enum
import math

from sqlalchemy import Column, Enum, Integer, JSON, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType, Building
from app.models.game.community.faction import FactionAdvantageScope
from app.models.game.defense import Defense, DefenseType
from app.models.game.event import PositionalEventType, PositionalEvent
from app.models.game.planet import PlanetArchetype
from app.models.game.settings import GalaxySettings
from app.models.game.ship import Ship, ShipType
from app.models.game.system import System
from logger import logger


# ── Vivres, population et stabilite ───────────────────────────────────────────
#
# Trois grandeurs liees par une seule boucle, jouee a chaque `update_view` :
#
#   la ferme remplit la reserve de vivres  ->  la population mange  ->  si elle
#   a mange a sa faim elle croit et le monde s'apaise ; sinon elle stagne et la
#   stabilite descend, ce qui fait baisser toute la production du territoire.
#
# Les constantes sont ici, en clair, plutot que dispersees dans le calcul :
# c'est la table de reglage du cycle de vie, et le seul endroit ou en changer
# le rythme.

#: Vivres consommes par habitant et par heure. 100 habitants mangent 5/h.
FOOD_PER_POPULATION_HOUR = 0.05

#: Croissance horaire d'une population bien nourrie et loin de sa limite.
POPULATION_GROWTH_RATE = 0.02

#: Population de reference quand le monde est vide : sans elle, une planete
#: tombee a zero habitant ne repartirait jamais (0 x 2% = 0).
POPULATION_SEED = 10

STABILITY_MAX = 100
STABILITY_MIN = 0

#: Points de stabilite regagnes par heure sur un monde nourri.
STABILITY_RECOVERY_HOUR = 2.0

#: Points perdus par heure sur un monde totalement affame. Une famine partielle
#: en perd d'autant moins qu'elle a mange.
STABILITY_DECAY_HOUR = 5.0

#: Part de la production encore assuree a stabilite nulle. Un monde en colere
#: tourne au ralenti, il ne s'arrete pas : sinon rien ne pourrait plus le sortir
#: de la.
STABILITY_FLOOR_FACTOR = 0.5


class ResourceType(enum.Enum):
    # Raw materials, extracted by the mater_extractor. Which of them a given
    # territory can produce at all depends on its planet archetype.
    iron = "iron"
    carbon = "carbon"
    silicium = "silicium"
    titanium = "titanium"
    cristal = "cristal"
    uranium = "uranium"
    hydrogen = "hydrogen"
    neutronium = "neutronium"

    # Produced by dedicated buildings, not by extraction.
    credits = "credits"
    energy = "energy"
    food = "food"
    population = "population"
    tritium = "tritium"

    def __str__(self):
        # Without this, `str(ResourceType.iron)` yields "ResourceType.iron" and
        # every serialized cost/gain key carries the class prefix, which no
        # client can map onto a field name.
        return self.name

    @classmethod
    def materials(cls):
        """Extractable materials, in display order."""
        return [
            cls.iron, cls.carbon, cls.silicium, cls.titanium,
            cls.cristal, cls.uranium, cls.hydrogen, cls.neutronium,
        ]

    @classmethod
    def stocks(cls):
        """Resources persisted as a column on the territory."""
        return cls.materials() + [cls.credits, cls.food, cls.population, cls.tritium]


class Territory(Base):
    __tablename__ = 'territory'

    id = Column(Integer, primary_key=True)

    position_in_system = Column(Integer, nullable=False)
    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    name = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    iron = Column(Integer, default=10000, nullable=False)
    carbon = Column(Integer, default=4000, nullable=False)
    silicium = Column(Integer, default=2500, nullable=False)
    titanium = Column(Integer, default=0, nullable=False)
    cristal = Column(Integer, default=0, nullable=False)
    uranium = Column(Integer, default=0, nullable=False)
    hydrogen = Column(Integer, default=0, nullable=False)
    neutronium = Column(Integer, default=0, nullable=False)

    credits = Column(Integer, default=8000, nullable=False)
    tritium = Column(Integer, default=100, nullable=False)
    population = Column(Integer, default=100, nullable=False)

    # Reserve de vivres. Elle se remplit par la ferme et se vide a chaque heure
    # vecue par la population : c'est la seule ressource qui se consomme toute
    # seule, sans que le joueur ne construise quoi que ce soit.
    food = Column(Integer, default=1000, nullable=False)

    # Stabilite, de 0 a 100. Un monde nourri revient a 100 ; un monde affame y
    # descend, et ce qu'il produit descend avec elle.
    stability = Column(Integer, default=STABILITY_MAX, nullable=False)

    # Planet archetype: decides which materials can be extracted here.
    archetype = Column(Enum(PlanetArchetype), nullable=True)
    # Per-material richness drawn at creation: {"iron": 1.12, ...}
    deposits = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # We use json as text here to be sure compatible with all dbs.
    # This should not be necessary to query rows using this field
    characteristics = Column(JSON, nullable=True)

    buildings = relationship("Building", back_populates="territory")
    ships = relationship("Ship", back_populates="territory")
    defenses = relationship("Defense", back_populates="territory")

    system = relationship("System", back_populates="territories")
    territory_events = relationship(
        "PositionalEvent", 
        primaryjoin="and_(PositionalEvent.on_territory_id == Territory.id, PositionalEvent.archived_at == None)",
    )
    user = relationship("User", back_populates="territories")

    #: Resources that accrue over time from buildings. La population n'y figure
    #: pas : elle ne sort d'aucun batiment, elle croit d'elle-meme tant qu'elle
    #: mange — voir `_run_life_cycle`.
    PRODUCED_RESOURCES = ResourceType.materials() + [
        ResourceType.credits, ResourceType.food, ResourceType.tritium]

    def __init__(self, system, position_in_system, characteristics={}, archetype=None):
        self.system_id = system.id
        self.position_in_system = position_in_system
        self.characteristics = json.dumps(characteristics)
        # Resolu par `create` a partir du prefab quand il y en a un ; sinon
        # tire ici. L'archetype commande l'extraction, il n'est donc jamais
        # simplement recopie de ce que le client annonce.
        self.archetype = archetype or PlanetArchetype.draw()
        self.deposits = self.archetype.roll_deposits()

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def create(cls, system_id, position_in_system, characteristics={}, archetype=None, name=None):
        """
        Allocate a free position.
        ---
        :param position:
        :param archetype: forced archetype, drawn at random when omitted
        :param name: nom affichable du monde, tel que le client l'a baptise
        :return:
        """
        system = System.get(
            id=system_id
        )
        if not Territory.available(system, position_in_system):
            raise ValueError("Position is not available")
        if isinstance(archetype, str):
            archetype = PlanetArchetype.get_by_name(archetype)
        # `planeteScheme` porte le prefab tire par le client, et c'est lui qui
        # fait le lien avec l'archetype : quand il est connu de la table, il
        # tranche. Un client ne peut donc pas annoncer une apparence de monde
        # glace et un archetype de geante gazeuse.
        from_scheme = PlanetArchetype.for_scheme((characteristics or {}).get('planeteScheme'))
        if from_scheme is not None:
            archetype = from_scheme
        territory = Territory(
            system=system,
            position_in_system=position_in_system,
            characteristics=characteristics,
            archetype=archetype,
        )
        # Le nom envoye par le client etait jete : tous les territoires
        # revenaient sans nom, et les listes affichaient du vide.
        territory.name = name
        db.session.add(system)
        db.session.flush()

        for b_type in BuildingType:
            b = Building(
                territory_id=territory.id,
                type=b_type
            )
            db.session.add(b)
            territory.buildings.append(b)

        for d_type in DefenseType:
            d = Defense(
                territory_id=territory.id,
                type=d_type
            )
            territory.defenses.append(d)

        for s_type in ShipType:
            s = Ship(
                territory_id=territory.id,
                type=s_type
            )
            territory.ships.append(s)

        db.session.add(territory)
        db.session.flush()
        return territory

    @classmethod
    def available(cls, system, position_in_system):
        """
        Check position is free
        ---
        :type position: tuple
        :return:
        """
        from app.models.game.system import System
        query = db.session.query(Territory).join(System)\
            .filter(System.id == system.id)\
            .filter(cls.position_in_system == position_in_system)
        return not db.session.query(query.exists()).scalar()

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
        # La relation, et pas seulement la cle : `population_capacity` lit la
        # production, qui lit la faction du joueur. Renseignee ici, elle est
        # disponible tout de suite ; laissee a la cle seule, elle ne le serait
        # qu'apres un flush.
        self.user = user

        # Le stock de depart est celui du monde au moment ou on s'y installe :
        # les colonnes portent des valeurs par defaut, la galaxie decide de leur
        # echelle. Applique ici plutot qu'a la creation du territoire, parce
        # qu'un monde inhabite n'a pas de stock de depart — il a un stock.
        multiplier = GalaxySettings.value(self.galaxy_name, 'starting_resources_multiplier')
        if multiplier != 1.0:
            for resource in ResourceType.stocks():
                held = getattr(self, resource.name, 0) or 0
                setattr(self, resource.name, int(round(held * multiplier)))

        # Un monde ne commence pas en famine. La population de depart est la
        # meme partout, le plafond non : sur un caillou irradie elle serait
        # affamee des la premiere heure, et le monde serait ingouvernable avant
        # d'avoir servi. On s'y installe donc a la mesure de ce qu'il porte —
        # un avant-poste sur un caillou, une colonie sur un monde tempere.
        capacity = self.population_capacity
        if 0 < capacity < (self.population or 0):
            self.population = capacity

    def update_view(self):
        """
        Rattraper le temps ecoule depuis la derniere vue du territoire.
        ---
        Le rattrapage est chronologique, et il doit l'etre : chaque chantier
        termine change ce que le territoire produit, donc decoupe la periode en
        tranches ou la production n'est pas la meme. On avance de chantier en
        chantier, en creditant la tranche qui le precede aux niveaux d'alors,
        puis on monte le batiment. La derniere tranche va jusqu'a maintenant,
        aux niveaux courants.

        La borne de depart est lue une fois, au tout debut : `updated_at` porte
        un `onupdate`, et le moindre commit intermediaire la ramenerait a
        maintenant. La periode a rattraper se refermait alors sur elle-meme au
        milieu du calcul, et le rattrapage dependait de si la ligne etait sale.
        """
        logger.info(f"Updating territory {self.id} view")
        if not self.user_id:
            return
        now = datetime.utcnow()
        credited_until = self.updated_at

        # Du plus ancien au plus recent : l'ordre de la relation ne dit rien de
        # l'ordre des fins de chantier, et deux niveaux rattrapes a l'envers ne
        # produisent pas la meme chose.
        finished = sorted(
            (e for e in self.territory_events if e.finishing_at <= now),
            key=lambda e: e.finishing_at
        )

        elapsed = 0.0
        for event in finished:
            # La tranche qui precede le chantier, aux niveaux d'avant lui.
            elapsed += self._credit_production(since=credited_until, until=event.finishing_at)
            credited_until = event.finishing_at

            # Puis le chantier : c'est ici que le niveau monte.
            self._apply_modification(event=event)
            event.archive()

            # TODO other events ...

        for event in self.territory_events:
            if event.finishing_at <= now:
                continue
            if event.event_type in (PositionalEventType.defense, PositionalEventType.ship):
                # apply all def / ships increase
                duration_for_one = event.extra_args.get("unitaryDuration")
                quantity = event.extra_args.get("quantity")
                last_refresh = event.extra_args.get("lastRefresh", event.created_at)
                if type(last_refresh) == str:
                    last_refresh = datetime.fromisoformat(last_refresh)
                # `total_seconds()` et non `.seconds` : ce dernier ne rend que le
                # reste au-dela des journees entieres, et une commande laissee
                # deux jours ne sortait donc rien de ces deux jours.
                built_for = max(0.0, (now - last_refresh).total_seconds())
                quantity_builded = math.floor(min(quantity, built_for / duration_for_one))
                extra_args = event.extra_args
                # left quantity
                extra_args["quantity"] = quantity - quantity_builded
                extra_args["lastRefresh"] = now.isoformat()
                event.extra_args = extra_args

                if quantity_builded >= 1:
                    self._apply_modification(event=event, amount=quantity_builded)

        # La derniere tranche, aux niveaux atteints apres tous les chantiers.
        elapsed += self._credit_production(since=credited_until, until=now)

        # Apres la production, et pas avant : la recolte de la periode ecoulee
        # est disponible pour la nourrir. L'ordre inverse affamerait un monde
        # dont les fermes suffisent pourtant tout juste.
        self._run_life_cycle(hours=elapsed)

        logger.info(f"Territory {self.id} caught up", infos=dict(
            time_elapsed=elapsed,
            events_applied=len(finished),
            user_id=self.user_id,
            food=self.food,
            population=self.population,
            stability=self.stability,
        ))
        db.session.commit()

    def _credit_production(self, since, until):
        """
        Crediter la production des batiments entre deux instants.
        ---
        Aux niveaux courants : c'est a l'appelant de decouper la periode aux
        moments ou ces niveaux changent.

        `total_seconds()` et non `.seconds` : un `timedelta` range les journees
        a part, et `.seconds` n'est que le reste. Une absence de trois jours
        rendait zero heure, une de vingt-cinq heures en rendait une. Une borne a
        l'envers — horloge qui recule, chantier anterieur a la derniere vue — ne
        retire rien non plus : elle ne credite rien.

        :return: les heures effectivement creditees
        """
        hours = max(0.0, (until - since).total_seconds()) / 3600.0
        if hours <= 0:
            return 0.0

        increased_resources = {}
        for r in self.PRODUCED_RESOURCES:
            increased_resources[r] = self.get_hourly_gain(resource_type=r) * hours
            setattr(self, r.name, (getattr(self, r.name) or 0) + increased_resources[r])

        logger.info(f"Resources increased for territory {self.id}", infos=dict(
            increased_resources=increased_resources,
            time_elapsed=hours,
            user_id=self.user_id,
        ))
        return hours

    def _apply_modification(self, event, amount=1):
        """
        Appliquer un chantier : monter le batiment, livrer les unites.
        ---
        Ne credite aucune production. C'est `update_view` qui tient la
        chronologie, et lui seul sait quelle tranche de temps se joue a quels
        niveaux. Cette methode le faisait aussi, sur
        `(updated_at - finishing_at)` : une soustraction a l'envers, dont
        `.seconds` rendait le complement a vingt-quatre heures. Un batiment
        termine une heure apres la derniere vue offrait ainsi vingt-trois heures
        de production, en plus de la periode deja creditee par ailleurs.
        """
        if event.event_type == PositionalEventType.building:
            building_type = BuildingType.get_by_name(event.extra_args['name'])
            self.add(type=building_type, amount=amount)
        elif event.event_type in (PositionalEventType.ship, PositionalEventType.defense):
            if event.event_type == PositionalEventType.defense:
                el_type = DefenseType.get_by_name(event.extra_args['name'])
            elif event.event_type == PositionalEventType.ship:
                el_type = ShipType.get_by_name(event.extra_args['name'])
            self.add(type=el_type, amount=amount)

    def _run_life_cycle(self, hours):
        """
        Faire manger la population, la faire croitre, et regler la stabilite.
        ---
        Une seule passe, jouee sur les heures ecoulees depuis la derniere vue du
        territoire. Trois effets, dans cet ordre, parce que chacun depend du
        precedent :

          · on prend dans la reserve ce que la population reclame. Si la reserve
            ne suffit pas, on prend tout ce qu'il y a et le reste est une famine ;
          · une population rassasiee croit vers ce que les fermes peuvent
            nourrir, une population affamee stagne — elle ne meurt pas, la
            famine se paie en stabilite, pas en habitants ;
          · la stabilite remonte vers 100 quand on mange, descend quand on jeune,
            d'autant plus vite que la disette est severe.

        :param hours: heures ecoulees, en flottant
        """
        if hours <= 0:
            return

        needed = self.food_upkeep * hours
        available = max(0.0, float(self.food or 0))
        eaten = min(needed, available)
        # Laisse le flottant tel quel, comme le fait la boucle de production
        # juste au-dessus : c'est la colonne Integer qui tronque a l'ecriture.
        # Arrondir ici ferait disparaitre les fractions d'un tour trop court.
        self.food = available - eaten

        # Sans bouche a nourrir il n'y a pas de famine : un monde vide est
        # parfaitement stable, il n'est simplement pas peuple.
        fed = 1.0 if needed <= 0 else eaten / needed

        stability = float(self.stability if self.stability is not None else STABILITY_MAX)

        if fed >= 1.0:
            self._grow_population(hours=hours)
            self.stability = min(STABILITY_MAX, stability + STABILITY_RECOVERY_HOUR * hours)
        else:
            # La population stagne : aucune croissance n'est appliquee ici. La
            # famine se paie en stabilite, jamais en habitants.
            self.stability = max(
                STABILITY_MIN, stability - STABILITY_DECAY_HOUR * (1.0 - fed) * hours)

    def _grow_population(self, hours):
        """
        Croissance logistique vers ce que les fermes savent nourrir.
        ---
        La limite n'est pas un chiffre pose a la main : c'est exactement le
        nombre d'habitants que la recolte horaire couvre. Construire une ferme
        est donc la seule facon de faire monter une population — et une planete
        sterile n'en portera jamais beaucoup, quel que soit son niveau
        d'equipement.
        """
        capacity = self.population_capacity
        population = float(self.population or 0)
        if capacity <= 0 or population >= capacity:
            return

        # POPULATION_SEED tient lieu de plancher : une planete repeuplee a zero
        # doit pouvoir repartir, or 0 x taux vaut 0.
        base = max(population, POPULATION_SEED)
        growth = POPULATION_GROWTH_RATE * base * (1.0 - population / capacity) * hours
        self.population = min(float(capacity), population + growth)

    @property
    def food_upkeep(self):
        """Vivres consommes par heure par la population en place."""
        return (self.population or 0) * FOOD_PER_POPULATION_HOUR

    @property
    def population_capacity(self):
        """
        Habitants que ce monde peut porter.
        ---
        Ce que la recolte horaire nourrit, corrige par l'habitabilite.

        L'habitabilite joue donc deux fois : une premiere sur ce que la ferme
        sort du sol, une seconde ici. C'est voulu. Sans la seconde, un monde
        accueillant ne serait qu'un monde qui recolte un peu plus, et l'ecart
        entre une planete temperee et un caillou irradie ne se verrait pas —
        or c'est precisement ce que le joueur choisit quand il colonise.

        Zero pour un monde sans proprietaire : la production depend du joueur
        (sa faction notamment), et un monde inhabite n'en a pas.
        """
        if not self.user_id or not FOOD_PER_POPULATION_HOUR:
            return 0
        harvest = self.get_hourly_gain(resource_type=ResourceType.food)
        fed = harvest / FOOD_PER_POPULATION_HOUR
        return int(fed * self.planet_archetype.habitability_factor)

    @property
    def population_growth(self):
        """
        Croissance horaire annoncee au joueur, zero pendant une famine.
        ---
        Meme formule que `_grow_population`, sur une heure : c'est ce que le
        client affiche a cote de la population, et il ne doit pas promettre une
        croissance que le prochain tour ne rendra pas.
        """
        if not self.user_id or self.is_starving:
            return 0.0
        capacity = self.population_capacity
        population = float(self.population or 0)
        if capacity <= 0 or population >= capacity:
            return 0.0
        base = max(population, POPULATION_SEED)
        return POPULATION_GROWTH_RATE * base * (1.0 - population / capacity)

    @property
    def food_balance(self):
        """Solde horaire de vivres : recolte moins consommation."""
        if not self.user_id:
            return 0.0
        return self.get_hourly_gain(resource_type=ResourceType.food) - self.food_upkeep

    @property
    def is_starving(self):
        """
        La reserve est vide et la recolte ne couvre pas les besoins.

        C'est l'etat que le joueur doit voir venir : population figee, stabilite
        qui descend, production qui suit.
        """
        return (self.food or 0) <= 0 and self.food_balance < 0

    @property
    def stability_score(self):
        """
        Stabilite affichable : un entier de 0 a 100.

        La colonne porte un flottant entre deux ecritures — le tour de jeu y
        ajoute des fractions d'heure — et un client qui attend un entier ne
        saurait pas quoi en faire.
        """
        stability = self.stability if self.stability is not None else STABILITY_MAX
        return int(max(STABILITY_MIN, min(STABILITY_MAX, stability)))

    @property
    def stability_factor(self):
        """
        Ce que la stabilite laisse de la production, entre STABILITY_FLOOR_FACTOR
        et 1.0.

        Un monde a 100 produit exactement ce qu'il produisait avant que la
        stabilite existe : les territoires deja en jeu ne perdent rien.
        """
        return STABILITY_FLOOR_FACTOR + (1.0 - STABILITY_FLOOR_FACTOR) * (
            self.stability_score / float(STABILITY_MAX))

    def get_building(self, building_type):
        """
        ---
        :param building_type:
        :return:
        """
        return next(b for b in self.buildings if b.type == building_type)

    def get_hourly_gain(self, resource_type):
        """
        ---
        :return:
        """
        hourly_gain = 0  # TODO add a base gain on territory without any construction
        buildings = [b for b in self.buildings if resource_type in b.type_of_resource]
        if buildings:
            for b in buildings:
                hourly_gain += b.get_hourly_gain[resource_type]
        if resource_type == ResourceType.energy:
            # Volcanic crusts are worth drilling, icy ones are not.
            hourly_gain *= self.planet_archetype.energy_factor
        if self.user.faction:
            hourly_gain = self.user.faction.apply(
                obj=hourly_gain,
                advantage_scope=FactionAdvantageScope.Resource,
                scope=resource_type.name
            )
        return hourly_gain

    def add(self, type, amount):
        logger.info(f"Adding {amount} of {type} to territory {self.id}", infos=dict(
            type=type,
            amount=amount,
            territory_id=self.id
        ))
        if isinstance(type, ResourceType):
            # Energy is computed from buildings, never stocked.
            if type in ResourceType.stocks():
                setattr(self, type.name, (getattr(self, type.name) or 0) + amount)

        if isinstance(type, BuildingType):
            building = self.get_building(building_type=type)
            if building:
                building.level += amount

        if isinstance(type, DefenseType):
            next(filter(lambda d: d.type, self.defenses)).increment(count=amount)
        if isinstance(type, ShipType):
            next(filter(lambda s: s.type, self.ships)).increment(count=amount)

    def match_prerequisite(self, prerequisites):
        """
        Check if prerequisites are matched or not
        ---
        :param prerequisites: Prerequisites to increase or build something
        :type prerequisites: dict
        :return:
        """
        resources = self.resources
        logger.info(f"Checking prerequisites for territory {self.id}", infos=dict(
            prerequisites=prerequisites,
            resources=resources
        ))
        for k, val in prerequisites.items():
            if val > resources[ResourceType(k)]:
                logger.debug(f"Prerequisite not met: {k} requires {val} but only {resources[ResourceType(k)]} available")
                return False
        return True

    def can_be_increased(self, building_type):
        """
        Check if building can be increase of level
        ---
        :return:
        """
        building = next(b for b in self.buildings if b.type == building_type)
        return self.match_prerequisite(building.cost)

    def increase(self, building_type):
        """
        ---
        :return:
        """
        building = next(b for b in self.buildings if b.type == building_type)
        if building:
            # TODO self.spend(building.cost)
            return PositionalEvent.create(
                territory=self,
                user=self.user,
                duration=building.next_level_duration,
                event_type=PositionalEventType.building,
                extra_args={
                    'name': building.type.name,
                    'level': building.level
                }
            )
            # TODO do it after event finished --> self.add(type=building_type, amount=1)

    def build(self, type, item):
        """
        Build ships or defenses on the territory.
        ---
        """
        shipyard = self.get_building(building_type=BuildingType.shipyard)

        if type == PositionalEventType.ship:
            element = ShipType[item["type"]]
        elif type == PositionalEventType.defense:
            element = DefenseType[item["type"]]
        if not self.match_prerequisite(element.cost):
            raise ValueError(f"Cannot build {item['quantity']} {element.name}. Prerequisites not reached.")

        # Meme acceleration que les batiments : ce sont des chantiers du meme
        # territoire, et les separer donnerait une galaxie rapide sur ses
        # batiments et lente sur ses flottes.
        unitary_duration = element.duration(shipyard=shipyard) / GalaxySettings.value(
            self.galaxy_name, 'build_time_divider')
        return PositionalEvent.create(
            territory=self,
            user=self.user,
            duration=unitary_duration * item["quantity"],
            event_type=type,
            extra_args={
                "name": element.name,
                "quantity": item["quantity"],
                "initialQuantity": item["quantity"],
                "unitaryDuration": unitary_duration
            }
        )


    @property
    def energy(self):
        building = next(b for b in self.buildings if b.type == BuildingType.power_station)
        return building.get_hourly_gain[ResourceType.energy] - self.consumption

    @property
    def consumption(self):
        return functools.reduce(lambda acc, x: acc + x, [b.consumption for b in self.buildings])

    @property
    def resources(self):
        """
        Get current resource state on territory
        :return:
        """
        stocks = {r: getattr(self, r.name) or 0 for r in ResourceType.stocks()}
        stocks[ResourceType.energy] = self.energy
        return stocks

    @property
    def galaxy_name(self):
        """
        Galaxie du territoire.
        ---
        Un territoire appartient a un systeme, qui appartient a une galaxie :
        c'est la portee reelle de tout ce qu'un joueur possede.
        """
        return self.system.galaxy_name if self.system else None

    @property
    def planet_archetype(self):
        """Archetype of the world, telluric for rows predating the split."""
        return self.archetype or PlanetArchetype.telluric

    @property
    def deposit_richness(self):
        """Raw richness drawn for this world, 1.0 for rows predating the split."""
        deposits = self.deposits or {}
        if isinstance(deposits, str):  # JSON column written as text
            deposits = json.loads(deposits)
        return {
            material: float(deposits.get(material, 1.0))
            for material in self.planet_archetype.materials
        }

    @property
    def material_yields(self):
        """
        Extraction multiplier per material on this exact world.
        ---
        Archetype ratio x deposit richness. A material the archetype does not
        produce is simply absent: no extractor level can conjure it.
        """
        richness = self.deposit_richness
        return {
            material: ratio * richness.get(material, 1.0)
            for material, ratio in self.planet_archetype.yields.items()
        }

    @property
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'position': self.position_in_system,
            # Remonte a la racine du territoire : les listes cross-systeme
            # (/api/territories) n'ont pas a fouiller le systeme pour savoir
            # de quelle galaxie releve chaque monde.
            'galaxy_name': self.galaxy_name,
            'system': self.system.serialize,
            'buildings': {b.type.name: b for b in self.buildings},
            'characteristics': json.loads(self.characteristics) if self.characteristics else {},
            'archetype': self.planet_archetype.name,
            'archetype_label': self.planet_archetype.label,
            # `deposits` is the raw richness drawn for this world, `yields` the
            # extraction multiplier actually applied (archetype x richness).
            'deposits': self.deposit_richness,
            'yields': self.material_yields,
            'resources': dict(
                {k.name: v for k, v in self.resources.items()},
                # La stabilite voyage avec les ressources parce que le client
                # l'affiche a cote d'elles, mais elle ne s'echange ni ne se
                # depense : elle n'est pas un `ResourceType`.
                stability=self.stability_score,
            ),
            # Ce que la population prend chaque heure, en face de ce que les
            # batiments rendent. Sans ca le client afficherait une recolte brute
            # et le joueur ne comprendrait pas pourquoi sa reserve fond.
            'upkeep': {ResourceType.food.name: self.food_upkeep},
            'stability': self.stability_score,
            # Le profil du monde : ce que le joueur lit pour juger une
            # planete avant de s'y installer. Des nombres, pas des phrases —
            # les libelles sont au client, les regles au serveur.
            'habitability': self.planet_archetype.habitability,
            'habitability_factor': self.planet_archetype.habitability_factor,
            'energy_factor': self.planet_archetype.energy_factor,
            'population_capacity': self.population_capacity,
            'population_growth': self.population_growth,
            'starving': self.is_starving,
            'updated_at': self.updated_at.isoformat(),
        }
