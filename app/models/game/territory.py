import functools
import json
from datetime import datetime, timedelta
import enum
import math

from sqlalchemy import (
    Boolean, Column, Enum, Integer, JSON, String, DateTime, ForeignKey, func)
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType, Building
from app.models.game.modifiers import (
    NO_MODIFIERS, ModifierScope, ModifierType)
from app.models.game.defense import Defense, DefenseType
from app.models.game.event import PositionalEventType, PositionalEvent
from app.models.game.fleet import Fleet
from app.models.game.planet import (
    PlanetArchetype, SETTLEMENT_STATION)
from app.models.game.settings import GalaxySettings
from app.models.game.ship import ShipType
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

#: Points perdus par heure sur un monde coupe du reseau imperial.
#:
#: Trois fois plus lent que la famine, et c'est voulu : l'isolement ronge, la
#: faim tue. Cent points a 1,5 par heure font soixante-sept heures avant
#: l'extinction, plus le sursis de secession — pres de six jours pour reagir.
#: Une absence de week-end ne coute pas un monde.
STABILITY_ISOLATION_HOUR = 1.5

#: Jours passes a zero avant qu'un monde ne fasse secession.
#:
#: A zero il est eteint, pas perdu : la fenetre existe pour qu'un joueur absent
#: puisse rentrer et rattraper. Passe ce delai, le monde entre dans le jeu des
#: autres.
SECESSION_DAYS = 3

#: Hydrogene consomme par unite de tritium produite par le craqueur.
CRACKING_RATIO = 4.0

#: Ce qu'une plateforme orbitale accepte de construire.
#:
#: Quatre modules, et pas un de plus : sans population, une ferme ne nourrit
#: personne, une academie n'a pas de chercheurs et un centre economique n'a pas
#: de marche. Ce qui reste tourne sans habitants — on extrait, on raffine, on
#: alimente, on entrepose.
ORBITAL_MODULES = frozenset({
    BuildingType.mater_extractor,
    BuildingType.power_station,
    BuildingType.depot,
    BuildingType.gas_cracker,
})


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

    # Donnees de recherche. Produites par l'academie, elles ne se posent sur
    # aucun monde : la reserve est imperiale et vit sur `User.research`, parce
    # que l'arbre technologique l'est aussi. Absente de `stocks()` pour cette
    # raison — il n'y a pas de colonne `research` sur le territoire.
    research = "research"

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


def _indexed(offer):
    """
    Ajoute la forme INDEXEE des prerequis a une offre de prise.

    `JsonUtility`, le seul lecteur JSON du client Unity, ne sait pas
    deserialiser un objet dont les cles sont inconnues a la compilation : il
    apparie par nom de CHAMP. Un dictionnaire `{"forage": 3}` ne peut donc pas
    etre lu, et la console web, elle, prefere le dictionnaire.

    On sert les deux. Meme raison et meme forme que
    `technology_type.describe()`, qui a paye cette lecon avant nous.
    """
    offer['requires_list'] = [
        {'name': name, 'level': level}
        for name, level in sorted((offer.get('requires') or {}).items())
    ]
    return offer


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

    # Stabilite, de 0 a 100. Un monde nourri et raccorde revient a 100 ; un
    # monde affame ou coupe du reseau y descend, et ce qu'il produit descend
    # avec elle.
    stability = Column(Integer, default=STABILITY_MAX, nullable=False)

    # Depuis quand la stabilite est a zero. Nul tant qu'elle ne l'est pas.
    # C'est cette date qui declenche la secession, et c'est elle qui donne au
    # joueur absent une fenetre pour rentrer : un monde a zero est eteint, il
    # n'est pas encore perdu.
    unstable_since = Column(DateTime, nullable=True)

    # Plateforme orbitale plutot que colonie. Un territoire orbital possede le
    # corps sans l'habiter : pas de population, donc pas de famine, et seuls
    # les modules d'`ORBITAL_MODULES` s'y construisent.
    orbital = Column(Boolean, default=False, nullable=False)

    # Capitale du joueur DANS CETTE GALAXIE. Elle est raccordee par definition :
    # l'isolement se mesure en chemin jusqu'a elle, et non en nombre de lignes.
    # Sans ce point fixe, deux mondes perdus relies l'un a l'autre se
    # declareraient tous deux raccordes.
    is_capital = Column(Boolean, default=False, nullable=False)

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
    defenses = relationship("Defense", back_populates="territory")

    # Les vaisseaux ne pendent plus au territoire : ils appartiennent aux
    # flottes du systeme, et se lisent par `Fleet.in_orbit_of`. Ce qu'un
    # chantier planetaire produit se retrouve en orbite, dans une flotte --
    # voir `app/models/game/fleet.py`.

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

        # Recevoir un monde, c'est devenir jouable. `User.new` ne pose l'arbre
        # que lorsqu'un territoire accompagne la creation du compte : un compte
        # cree sans monde — l'administrateur, par exemple — puis installe plus
        # tard jouait sans une seule technologie, et son ecran de recherche
        # n'ouvrait aucune fiche.
        from app.models.game.technologies.technology import Technology
        Technology.ensure(user)

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

        # Pour la meme raison : l'hydrogene sorti dans cette tranche de temps
        # est craquable tout de suite, sans attendre le tour suivant.
        self._run_cracking(hours=elapsed)

        # Et le commerce en dernier : ce qui vient d'etre produit et craque part
        # sur les lignes dans la meme tranche, plutot que d'attendre un tour.
        self._run_trade(hours=elapsed)

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

        # Les Donnees ne se posent pas sur le monde qui les produit : l'academie
        # travaille pour l'empire, et l'arbre technologique est imperial. Elles
        # vont donc a la reserve du joueur, ou toutes les academies versent.
        research = self.get_hourly_gain(resource_type=ResourceType.research) * hours
        if research:
            increased_resources[ResourceType.research] = research
            self.user.add_research(research)

        logger.info(f"Resources increased for territory {self.id}", infos=dict(
            increased_resources=increased_resources,
            time_elapsed=hours,
            user_id=self.user_id,
        ))
        return hours

    def _apply_modification(self, event, amount=None):
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
            self.add(type=building_type, amount=amount if amount is not None else 1)
            return

        if event.event_type not in (PositionalEventType.ship, PositionalEventType.defense):
            return

        # Un chantier arrive a terme livre tout ce qu'il lui restait a livrer.
        # La boucle horaire ne credite que les unites sorties avant la derniere
        # vue et decompte `quantity` a mesure ; ce qui reste dans ce champ au
        # moment de l'archivage est precisement le solde. La valeur figee a 1
        # qui se trouvait ici livrait une unite pour une commande de dix, et
        # les neuf autres disparaissaient avec l'evenement.
        delivered = amount if amount is not None else event.extra_args.get('quantity', 1)
        if delivered <= 0:
            return

        if event.event_type == PositionalEventType.defense:
            self.add(type=DefenseType.get_by_name(event.extra_args['name']), amount=delivered)
        else:
            self._deliver_ships(
                event=event,
                ship_type=ShipType.get_by_name(event.extra_args['name']),
                amount=delivered,
            )

    def _deliver_ships(self, event, ship_type, amount):
        """
        Remettre a une flotte les vaisseaux qui sortent du chantier.
        ---
        Le territoire assemble, il ne detient pas : ce qui sort du chantier
        appartient a une flotte du systeme. Laquelle est decide par
        `Fleet.receive_construction`, sur ce qui se trouve en orbite d'ici.

        La flotte retenue est notee sur l'evenement pour que les livraisons
        suivantes de la meme commande la retrouvent, plutot que d'en creer une
        par vaisseau.
        """
        args = event.extra_args
        fleet = Fleet.receive_construction(
            territory=self,
            user=self.user,
            memo_fleet_id=args.get('fleetId'),
            spawn=args.get('spawn'),
        )
        fleet.add_ships(ship_type=ship_type, amount=amount)

        if args.get('fleetId') != fleet.id:
            args['fleetId'] = fleet.id
            event.extra_args = args

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

        # Deux moteurs, et ils s'additionnent : un monde qu'on assiege ET qu'on
        # affame tombe en une nuit, la ou chacun pris seul laisse des jours.
        # L'isolement ronge, la faim tue.
        isolation = 0.0 if self.is_connected else STABILITY_ISOLATION_HOUR

        if fed >= 1.0 and not isolation:
            self._grow_population(hours=hours)
            self.stability = min(STABILITY_MAX, stability + STABILITY_RECOVERY_HOUR * hours)
        else:
            if fed >= 1.0:
                # Nourri mais coupe : la population croit quand meme. Ce n'est
                # pas la faim qui la retient, c'est le reste de l'empire qui
                # manque.
                self._grow_population(hours=hours)

            # La population stagne : aucune croissance n'est appliquee ici. La
            # famine se paie en stabilite, jamais en habitants.
            famine = STABILITY_DECAY_HOUR * (1.0 - fed)
            self.stability = max(
                STABILITY_MIN, stability - (famine + isolation) * hours)

        # Le compte a rebours de la secession, et la secession elle-meme.
        self._check_secession()

    @property
    def growth_rate(self):
        """
        Taux de croissance horaire, modificateurs compris.
        ---
        Lu par le calcul (`_grow_population`) comme par l'annonce
        (`population_growth`). Deux lectures du meme taux : promettre au client
        une croissance que le tour suivant ne rendrait pas est la faute que
        cette propriete existe pour eviter.
        """
        return self.modifiers.apply(
            value=POPULATION_GROWTH_RATE,
            scope=ModifierScope.Territory,
            modifier_type=ModifierType.Production,
            target='population_growth',
        )

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
        growth = self.growth_rate * base * (1.0 - population / capacity) * hours
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
        # Une plateforme orbitale ne porte personne : il n'y a pas de sol ou
        # poser une ville, et c'est toute la difference entre les deux gestes.
        if self.orbital:
            return 0
        if not self.user_id or not FOOD_PER_POPULATION_HOUR:
            return 0
        harvest = self.get_hourly_gain(resource_type=ResourceType.food)
        fed = harvest / FOOD_PER_POPULATION_HOUR
        capacity = fed * self.planet_archetype.habitability_factor

        # Adaptation extreme et Terraformation agissent ici, et nulle part
        # ailleurs : elles ne font pas pousser plus de ble, elles font tenir
        # plus de monde sur la meme recolte.
        return int(self.modifiers.apply(
            value=capacity,
            scope=ModifierScope.Territory,
            modifier_type=ModifierType.Capacity,
            target=ResourceType.population.name,
        ))

    # ── Le craqueur ─────────────────────────────────────────────────────────

    @property
    def cracking_capacity(self):
        """
        Tritium que le craqueur sortirait en une heure, hydrogene a volonte.

        Ce que le module rend VRAIMENT est borne par l'hydrogene en reserve :
        voir `_run_cracking`. Cette valeur-ci est ce que le client annonce, et
        ce qu'un joueur compare au niveau suivant.
        """
        cracker = self.get_building(building_type=BuildingType.gas_cracker)
        level = cracker.level or 0
        if level <= 0 or not self.accepts(BuildingType.gas_cracker):
            return 0.0

        # Meme forme que la raffinerie, trois fois plus haut : craquer une
        # geante doit valoir mieux que raffiner de l'eau, sans rendre la
        # raffinerie inutile sur les mondes qui en ont.
        return 35.0 * level * pow(1.1, level) * self.stability_factor

    def _run_cracking(self, hours):
        """
        Casse l'hydrogene en tritium, dans la limite de ce qu'il y a en reserve.

        Le seul batiment du jeu dont l'ENTREE est une ressource. Il ne figure
        donc pas dans `PRODUCED_RESOURCES` : une production qui consomme ne se
        decrit pas par une courbe seule, et la laisser dans la boucle generale
        aurait fait descendre une colonne sous zero.

        Joue APRES la production : l'hydrogene extrait dans la meme tranche de
        temps est craquable tout de suite, ce qui evite qu'une plateforme
        n'attende un tour pour transformer ce qu'elle vient de sortir.
        """
        if hours <= 0:
            return 0.0

        wanted = self.cracking_capacity * hours
        if wanted <= 0:
            return 0.0

        available = max(0.0, float(self.hydrogen or 0))
        made = min(wanted, available / CRACKING_RATIO)
        if made <= 0:
            return 0.0

        self.hydrogen = available - (made * CRACKING_RATIO)
        self.tritium = (self.tritium or 0) + made
        return made

    # ── Le commerce ─────────────────────────────────────────────────────────

    #: Ce qui circule sur une ligne. Ni l'energie, qui se produit et se consomme
    #: sur place sans stock, ni la population, qui voyage en vaisseau de
    #: colonisation ou ne voyage pas.
    TRADEABLE = frozenset(
        ResourceType.materials()
        + [ResourceType.credits, ResourceType.food, ResourceType.tritium])

    def _run_trade(self, hours):
        """
        Fait couler les lignes dont ce territoire est le DEPART.

        Le depart seulement, et c'est ce qui evite de compter deux fois : les
        deux bouts se mettent a jour chacun de leur cote, et une ligne jouee par
        les deux transporterait le double. Les flux vont dans les deux sens
        malgre cela — c'est la ligne qui est parcourue, pas la direction.

        :return: {nom de ressource: quantite deplacee}, pour la trace.
        """
        if hours <= 0 or not self.user_id:
            return {}

        from app.models.game.trade import TradeLine

        moved = {}
        # Meme raison que pour le raccordement : la lecture des lignes ne doit
        # pas ecrire `updated_at` au milieu du tour.
        with db.session.no_autoflush:
            lines = [
                line for line in TradeLine.of(user=self.user)
                if line.origin_id == self.id
            ]

        for line in lines:
            if line.is_blockaded:
                # Un robinet, pas une demolition : la ligne reste ouverte et
                # recoulera des que la flotte hostile s'en ira.
                continue

            other = line.destination
            if other is None or other.user_id != self.user_id:
                continue

            budget = line.throughput * hours
            for flow in line.flows:
                if budget <= 0:
                    break
                shifted = self._shift(
                    flow=flow, other=other, budget=budget, hours=hours)
                if shifted:
                    budget -= shifted[1]
                    moved[shifted[0]] = moved.get(shifted[0], 0.0) + shifted[1]

        return moved

    def _shift(self, flow, other, budget, hours):
        """
        Deplace un flux, borne par le debit restant et par ce qu'il y a en stock.

        Le debit declare est HORAIRE : sur deux heures il deplace deux fois
        plus. Le traiter comme une quantite absolue faisait d'une ligne un
        transfert unique, quelle que soit la duree ecoulee.

        :return: (nom de ressource, quantite) ou None si rien n'a bouge.
        """
        name = (flow or {}).get('resource')
        try:
            resource = ResourceType(name)
        except ValueError:
            return None

        if resource not in self.TRADEABLE:
            return None

        rate = float(flow.get('rate') or 0)
        if rate <= 0:
            return None

        # `to_origin` : le sens du flux sur la ligne. Faux — le defaut — va du
        # depart vers l'arrivee.
        towards_origin = bool(flow.get('to_origin'))
        source, target = (other, self) if towards_origin else (self, other)

        available = float(getattr(source, resource.name, 0) or 0)
        amount = min(rate * hours, budget, available)
        if amount <= 0:
            return None

        setattr(source, resource.name, available - amount)
        setattr(target, resource.name,
                float(getattr(target, resource.name, 0) or 0) + amount)
        return resource.name, amount

    # ── Prendre ce monde ────────────────────────────────────────────────────

    @property
    def is_claimed(self):
        return self.user_id is not None

    def settlement_kind(self):
        """
        Le geste que ce corps accepte : `colony` ou `station`.
        ---
        Lu de l'archetype, jamais decide ici : c'est la table des archetypes qui
        dit ce qu'un monde est, et deux endroits qui en decideraient
        finiraient par ne plus dire la meme chose.
        """
        archetype = self.planet_archetype
        return archetype.settlement if archetype is not None else None

    def claim_refusal(self, user):
        """
        Ce qui empeche ce joueur de prendre ce monde, `None` s'il le peut.

        Rend une PHRASE, pas un booleen : un bouton eteint sans raison envoie
        chercher au mauvais endroit, et c'est ici qu'on sait pourquoi. Ne
        verifie ni la flotte ni la coque — cela depend de ce qui est en orbite,
        que le modele de territoire n'a pas a interroger.
        """
        from app.models.game.technologies.technology import Technology

        if self.is_claimed:
            return "This world already has an owner."

        archetype = self.planet_archetype
        if archetype is None:
            return "This world has no archetype and cannot be claimed."

        if archetype.settlement == SETTLEMENT_STATION:
            required = archetype.station_requires
        else:
            required = archetype.colonisation_requires()
            if required is None:
                # Ne devrait pas arriver : la table des paliers couvre tous les
                # archetypes colonisables. Le dire plutot que de laisser passer.
                return "No known method settles a %s world." % archetype.name

        levels = Technology.levels(user=user)
        missing = {
            name: level for name, level in (required or {}).items()
            if levels.get(name, 0) < level
        }
        if missing:
            return "Requires: %s." % ", ".join(
                "%s %d" % (name, level) for name, level in sorted(missing.items()))

        return None

    def claim_offer(self, user=None):
        """
        Ce qu'il faudrait pour prendre ce monde, tel que le client doit l'afficher.

        Rend le geste, la coque a amener, ce qui manque et — quand il y a un
        refus — la phrase a montrer. Le client dessine son bouton a partir de
        la : recopier la regle des archetypes cote client la ferait diverger au
        premier equilibrage, et c'est deja arrive a d'autres tables de ce jeu.

        `user` par defaut : celui de la session. Le territoire n'est pas oblige
        de le savoir, mais toutes les lectures passent par une route
        authentifiee, et le demander a l'appelant a chaque serialisation
        obligerait a le faire descendre partout.
        """
        from app.models.game.planet import SETTLEMENT_COLONY

        if user is None:
            user = self._current_user()

        archetype = self.planet_archetype
        kind = archetype.settlement if archetype is not None else SETTLEMENT_COLONY
        station = kind == SETTLEMENT_STATION

        offer = {
            'kind': kind,
            # La coque a amener en orbite. Le premier monde d'une galaxie n'en
            # demande aucune — un joueur qui n'a rien ne peut pas en avoir
            # construit — et `hull` est alors nul.
            'hull': ShipType.ExtractionPlatform.name if station else ShipType.ColonyShip.name,
            'requires': (archetype.station_requires if station
                         else (archetype.colonisation_requires() or {})),
            'taken': self.is_claimed,
            'available': False,
            'first': False,
            'refusal': None,
        }

        if user is None:
            # Lecture anonyme : on decrit le monde, on ne promet rien.
            offer['refusal'] = "Sign in to claim a world."
            return _indexed(offer)

        # La premiere prise d'une galaxie ne demande ni coque ni technologie,
        # seulement un monde tellurique. C'est un cas a part, et le dire evite
        # au client d'aller chercher une coque qu'il ne peut pas avoir.
        settled = any(t.galaxy_name == self.galaxy_name
                      for t in (user.territories or []))
        if not settled:
            offer['first'] = True
            offer['hull'] = None
            offer['requires'] = {}
            if self.is_claimed:
                offer['refusal'] = "This world already has an owner."
            elif archetype != PlanetArchetype.telluric:
                offer['refusal'] = (
                    "A starting world must be telluric, not %s."
                    % (archetype.name if archetype else "unknown"))
            else:
                offer['available'] = True
            return _indexed(offer)

        refusal = self.claim_refusal(user=user)
        offer['refusal'] = refusal
        offer['available'] = refusal is None
        return _indexed(offer)

    @staticmethod
    def _current_user():
        """
        Le joueur de la session, `None` hors requete.
        ---
        Lu ici plutot que passe en argument : la serialisation est appelee par
        une dizaine de routes, et faire descendre le joueur jusqu'a elle
        toucherait chacune pour un champ.
        """
        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return None
            return current_user.get()
        except Exception:  # noqa: BLE001 - hors contexte de requete
            return None

    def claim(self, user, now=None):
        """
        Attribue ce monde au joueur, en colonie ou en plateforme.

        C'est le chemin unique : la premiere attribution d'une galaxie, la
        colonisation et l'arrimage d'une plateforme passent tous par ici. Ce qui
        les distingue — une coque en orbite, un monde deja tenu — se verifie
        avant, dans la route.
        """
        now = now or datetime.utcnow()
        orbital = self.settlement_kind() == SETTLEMENT_STATION

        self.orbital = orbital
        self.assign(user=user)

        if orbital:
            # Une plateforme ne porte personne. `assign` a pu laisser la
            # population par defaut du monde : on la vide, sans quoi une
            # plateforme mangerait — et mourrait de faim.
            self.population = 0
            self.food = 0

        # La premiere prise dans une galaxie fait la capitale. C'est le point
        # fixe du reseau : l'isolement se mesure en chemin jusqu'a elle.
        if not self.capital_of(user=user, galaxy_name=self.galaxy_name):
            self.is_capital = True

        self.stability = STABILITY_MAX
        self.unstable_since = None
        return self

    # ── Tenir ce monde ──────────────────────────────────────────────────────

    @property
    def is_connected(self):
        """
        Ce monde est-il raccorde au reseau imperial ?

        Il l'est s'il existe un chemin jusqu'a la CAPITALE du joueur dans cette
        galaxie, par des lignes de commerce ouvertes et non bloquees ; deux
        territoires d'un meme systeme sont raccordes sans ligne.

        La capitale l'est par definition — sans ce point fixe, deux mondes
        perdus relies l'un a l'autre se declareraient tous deux raccordes, ce
        qui viderait la regle de son sens.

        Un monde sans proprietaire n'est ni raccorde ni isole : il ne perd rien,
        il attend. Rendre `True` plutot que `False` evite qu'un monde en
        secession ne continue de s'etioler.
        """
        if not self.user_id:
            return True
        if self.is_capital:
            return True

        # `no_autoflush` : lire le reseau demande des requetes, et une requete
        # au milieu du tour de jeu declenche un flush — qui ecrit `updated_at`
        # par son `onupdate`, c'est-a-dire le jalon meme depuis lequel le tour
        # compte son temps ecoule. Un chantier y perdait une unite sur les
        # commandes les plus longues. Le raccordement est une LECTURE : il n'a
        # aucune raison d'ecrire quoi que ce soit.
        with db.session.no_autoflush:
            return self._connected_to_capital()

    def _connected_to_capital(self):
        capital = Territory.capital_of(user=self.user, galaxy_name=self.galaxy_name)
        if capital is None:
            # Aucune capitale : le joueur n'est entre dans cette galaxie par
            # aucun chemin de prise — un monde attribue a la main, un univers de
            # test. On ne va pas l'affamer pour cela.
            return True

        return self._reaches(capital)

    def _reaches(self, capital):
        """
        Parcours du reseau, du monde vers la capitale.
        ---
        Sur les territoires du joueur DANS CETTE GALAXIE, et sur eux seuls : une
        ligne ne traverse pas les galaxies, et un monde tenu ailleurs ne raccorde
        rien ici.
        """
        from app.models.game.trade import TradeLine

        galaxy = self.galaxy_name
        mine = {
            territory.id: territory
            for territory in (self.user.territories or [])
            if territory.galaxy_name == galaxy
        }

        # Les voisins de systeme, gratuits : une plateforme vit de la colonie
        # d'a cote sans rien construire.
        neighbours = {}
        for territory in mine.values():
            neighbours.setdefault(territory.id, set())
            for other in mine.values():
                if other.id != territory.id and other.system_id == territory.system_id:
                    neighbours[territory.id].add(other.id)

        for line in TradeLine.of(user=self.user):
            if line.origin_id not in mine or line.destination_id not in mine:
                continue
            if line.is_blockaded:
                continue
            neighbours.setdefault(line.origin_id, set()).add(line.destination_id)
            neighbours.setdefault(line.destination_id, set()).add(line.origin_id)

        seen = {self.id}
        queue = [self.id]
        while queue:
            current = queue.pop()
            if current == capital.id:
                return True
            for neighbour in neighbours.get(current, ()):  # noqa: B007
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)

        return False

    @property
    def is_deactivated(self):
        """
        Stabilite a zero : le monde est eteint, pas perdu.
        ---
        Production nulle, chantiers geles. Il reste au joueur et remonte des
        qu'il est nourri ou raccorde — la secession ne vient qu'apres.
        """
        return self.stability_score <= STABILITY_MIN

    @property
    def secedes_at(self):
        """Quand ce monde fera secession, `None` s'il n'est pas a zero."""
        if not self.unstable_since:
            return None
        return self.unstable_since + timedelta(days=SECESSION_DAYS)

    def _check_secession(self, now=None):
        """
        Fait secession si le monde est reste a zero assez longtemps.

        Il part avec TOUT : stock, batiments, population. Celui qui l'a laisse
        partir perd ce qu'il y avait entasse, mais peut tout recuperer en le
        reprenant — la secession punit sans confisquer, et un monde riche a
        l'abandon devient une cible que les voisins ont une raison d'aller
        chercher.

        Les flottes ne partent pas avec lui : elles appartiennent au joueur, pas
        au territoire.
        """
        now = now or datetime.utcnow()

        if not self.user_id:
            return False
        if not self.is_deactivated:
            # Remonte au-dessus de zero : le compte a rebours s'efface. Teste
            # avant d'ecrire — reaffecter la meme valeur salit l'instance, et
            # une instance sale ecrit `updated_at` au prochain flush, c'est-a-
            # dire le jalon depuis lequel le tour de jeu compte son temps.
            if self.unstable_since is not None:
                self.unstable_since = None
            return False

        if self.unstable_since is None:
            self.unstable_since = now
            return False

        if now < self.unstable_since + timedelta(days=SECESSION_DAYS):
            return False

        logger.info("Territory %d secedes" % self.id, infos=dict(
            territory_id=self.id, user_id=self.user_id,
            since=self.unstable_since.isoformat()))

        # Une secession se lit dans le journal comme un geste : c'est un monde
        # qui change de main, et l'administrateur qui cherche pourquoi un joueur
        # a fondu doit pouvoir le retrouver.
        from app.models.audit import Action, record
        record(Action.TERRITORY_SECEDE, user_id=self.user_id,
               territory_id=self.id, galaxy=self.galaxy_name,
               was_capital=bool(self.is_capital))

        was_capital = bool(self.is_capital)
        former = self.user

        self.user_id = None
        self.user = None
        self.is_capital = False
        self.unstable_since = None

        # Les lignes qui y menaient ne menent plus nulle part.
        from app.models.game.trade import TradeLine
        for line in TradeLine.touching(territory=self):
            line.close(now=now)

        if was_capital:
            Territory.promote_capital(user=former, galaxy_name=self.galaxy_name)

        return True

    @classmethod
    def promote_capital(cls, user, galaxy_name):
        """
        Designe une nouvelle capitale apres la perte de l'ancienne.

        Sans elle, tous les mondes restants se declareraient isoles et
        tomberaient l'un apres l'autre : perdre sa capitale couterait l'empire
        entier, ce qui n'est pas une regle mais un effondrement.

        Le plus ancien monde encore tenu : c'est le plus etabli, et le choix ne
        demande rien au joueur a un moment ou il n'est probablement pas la.
        """
        if user is None or not galaxy_name:
            return None

        held = sorted(
            (t for t in (user.territories or [])
             if t.galaxy_name == galaxy_name and t.user_id == user.id),
            key=lambda t: t.id)
        if not held:
            return None

        chosen = held[0]
        chosen.is_capital = True
        logger.info("Capital promoted", infos=dict(
            territory_id=chosen.id, user_id=user.id, galaxy=galaxy_name))
        return chosen

    @classmethod
    def capital_of(cls, user, galaxy_name):
        """La capitale de ce joueur dans cette galaxie, `None` s'il n'en a pas."""
        if user is None or not galaxy_name:
            return None
        for territory in (user.territories or []):
            if territory.is_capital and territory.galaxy_name == galaxy_name:
                return territory
        return None

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
        return self.growth_rate * base * (1.0 - population / capacity)

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
        Le batiment de ce type sur ce monde, cree au niveau zero s'il manque.

        Les lignes sont posees une par type a la naissance du territoire : un
        type ajoute au jeu apres coup n'existe donc sur aucun monde deja cree,
        et cette methode levait alors un `StopIteration` nu — impossible a lire
        dans une trace, et fatal a la premiere lecture du monde. La migration
        pose les lignes manquantes ; ceci rattrape tout ce qu'elle aurait
        oublie, et rattrapera le prochain batiment ajoute.
        """
        found = next((b for b in self.buildings if b.type == building_type), None)
        if found is not None:
            return found

        from app.models.game.buildings import Building

        found = Building(territory_id=self.id, type=building_type)
        db.session.add(found)
        self.buildings.append(found)
        return found

    @property
    def modifiers(self):
        """
        Ce qui modifie les valeurs de ce monde : faction et recherche du
        proprietaire, dans un seul ensemble.

        Vide pour un monde sans proprietaire : la production depend du joueur,
        et il n'y en a pas.
        """
        return self.user.modifiers if self.user else NO_MODIFIERS

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

        # Faction ET recherche, empilees : `Extraction assistee` et le bonus
        # silicium des Technocrates s'additionnent ici, au meme endroit et par
        # le meme calcul. La version precedente n'interrogeait que la faction,
        # et aucune technologie n'aurait pu toucher a la production.
        return self.modifiers.apply(
            value=hourly_gain,
            scope=ModifierScope.Resource,
            modifier_type=ModifierType.Production,
            target=resource_type.name,
        )

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
            # `lambda d: d.type` est toujours vrai : le filtre ne filtrait rien
            # et c'est la premiere ligne de defense qui montait, quelle que soit
            # celle qu'on avait commandee. Une batterie de missiles livrait des
            # canons flack.
            defense = next((d for d in self.defenses if d.type == type), None)
            if defense is not None:
                defense.increment(count=amount)

        # Les vaisseaux ne passent pas par ici : ils vont a une flotte, pas au
        # territoire. Voir `_deliver_ships`.

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
            if not val:
                continue
            # `.get` et non `[]` : un cout peut nommer une ressource que le
            # territoire ne detient pas. Les Donnees sont dans ce cas — la
            # reserve de recherche appartient au joueur, pas au monde — et la
            # lecture directe levait un KeyError sur le premier batiment venu,
            # puisque `BuildingType.get_cost` enumere toutes les ressources.
            # Une ressource absente vaut zero : un cout non nul dessus est
            # simplement hors de portee de ce territoire, ce qui est vrai.
            held = resources.get(ResourceType(k), 0)
            if val > held:
                logger.debug(f"Prerequisite not met: {k} requires {val} but only {held} available")
                return False
        return True

    #: Ce qu'un cout exige sans jamais le consommer.
    #:
    #: · L'energie n'est pas un stock mais un solde : `Territory.energy` la
    #:   recalcule a chaque lecture depuis la centrale moins la consommation des
    #:   batiments. La debiter n'aurait aucun effet durable, et le cout en
    #:   energie d'un batiment est deja sa consommation permanente une fois
    #:   monte -- voir `Building.consumption`.
    #: · La population sert les batteries et arme les vaisseaux, elle n'est pas
    #:   brulee. La debiter deperait la colonie a chaque chantier, sans rien qui
    #:   la rende : la croissance est plafonnee par la nourriture, pas relancee
    #:   par les commandes.
    #:
    #: Si l'un des deux doit devenir consommable un jour, c'est ici et nulle
    #: part ailleurs.
    NON_CONSUMABLE = (ResourceType.energy, ResourceType.population)

    def spend(self, cost):
        """
        Debiter un cout des reserves du territoire.
        ---
        Le pendant de `match_prerequisite`, qui ne faisait que comparer : les
        couts etaient verifies et jamais payes. Un joueur franchissait le seuil
        une fois et montait ensuite tout ce qu'il voulait sans rien depenser,
        si bien que la seule monnaie du jeu etait le temps.

        Se prend un dictionnaire aux memes cles que la verification -- noms de
        ressources ou membres de `ResourceType`, les deux se rencontrent selon
        qu'on vienne d'un batiment ou d'un vaisseau.

        Aucune borne a zero : l'appelant a verifie qu'il pouvait payer, et
        rattraper ici un solde negatif masquerait la commande qui n'aurait pas
        du passer.
        """
        stocks = ResourceType.stocks()
        for resource, amount in cost.items():
            resource = ResourceType(resource)
            if not amount or resource in self.NON_CONSUMABLE:
                continue
            # Une ressource qui n'est pas une colonne du territoire ne se debite
            # pas ici : les Donnees se prennent sur le joueur, par
            # `User.spend_empire`. Sans ce filtre, le `setattr` poserait un
            # attribut fantome sur l'instance et la depense disparaitrait au
            # prochain chargement.
            if resource not in stocks:
                continue
            setattr(self, resource.name, (getattr(self, resource.name) or 0) - amount)

        logger.info(f"Spent resources on territory {self.id}", infos=dict(
            cost={str(ResourceType(k)): v for k, v in cost.items() if v},
            user_id=self.user_id,
        ))

    def place_refusal(self, building_type):
        """
        Pourquoi ce batiment n'a pas sa place ici, `None` s'il l'a.

        La question de PLACE seule, et c'est la seule dont la reponse soit
        definitive : une plateforme n'a pas de sol pour une ferme, et une geante
        gazeuse est le seul corps dont on puisse craquer les gaz. Ni attendre ni
        chercher n'y changera rien, la ou un manque de fer ou de technologie se
        rattrape.

        Separee de `build_refusal` parce que le client en a besoin seule : il
        efface ce qui n'aura jamais sa place, mais laisse a porte de clic ce
        qu'il manque seulement d'avoir les moyens de batir.
        """
        if self.orbital and building_type not in ORBITAL_MODULES:
            return (
                "Cannot build %s on an orbital platform. It has no ground: "
                "only %s can be built there." % (
                    building_type.name,
                    ", ".join(sorted(m.name for m in ORBITAL_MODULES))))

        # Le craqueur casse de l'hydrogene : sur un monde qui n'en sort pas, il
        # n'aurait rien a casser.
        if building_type == BuildingType.gas_cracker:
            archetype = self.planet_archetype
            if archetype is None or not archetype.produces(ResourceType.hydrogen.name):
                return ("Cannot build %s here: this world yields no hydrogen to "
                        "crack." % building_type.name)

        return None

    def accepts(self, building_type):
        """
        Ce monde accepte-t-il ce batiment, quel que soit le reste ?
        ---
        Repond a la question de PLACE, pas de moyens : les ressources et les
        technologies se verifient ailleurs.
        """
        return self.place_refusal(building_type) is None

    def construction_offer(self):
        """
        Ce que ce monde peut porter, et pourquoi il refuse le reste.

        Le client dressait sa liste de batiments depuis un registre code en dur :
        il offrait donc une ferme et une academie sur une plateforme orbitale,
        que le serveur refusait ensuite. Une regle recopiee dans deux clients
        diverge au premier equilibrage — c'est le serveur qui la dit, comme pour
        `claim_offer`.

        Les refus portent leur phrase : un batiment simplement absent de la
        liste laisserait le joueur chercher pourquoi.
        """
        accepted = []
        refused = []

        for building_type in BuildingType:
            reason = self.place_refusal(building_type)
            if reason is None:
                accepted.append(building_type.name)
            else:
                refused.append({'name': building_type.name, 'reason': reason})

        return {
            'orbital': bool(self.orbital),
            'accepts': accepted,
            'refusals': refused,
        }

    def holding_status(self, user=None):
        """
        Ce qu'il en est de la tenue de ce monde : raccorde, eteint, et quand il
        partira s'il reste ainsi.

        Rendu au SEUL proprietaire qui regarde, et `None` a tout autre. Deux
        raisons, et les deux comptent :

          · Dire d'un monde ennemi qu'il est isole publierait la carte de son
            reseau, que rien dans le jeu ne permet d'observer autrement. Un
            joueur saurait ou frapper sans avoir rien explore.

          · Le raccordement se calcule par un parcours du reseau du
            proprietaire. Le faire pour chaque monde affiche d'un systeme
            etranger couterait autant de parcours que de mondes, pour une
            reponse que personne n'a le droit de lire.

        Le client, lui, ne le consulte que sur ses propres mondes : un bloc
        absent n'y change rien.
        """
        watcher = user if user is not None else self._current_user()
        if watcher is None or not self.user_id or self.user_id != watcher.id:
            return None

        secedes = self.secedes_at
        return {
            # Ce drapeau n'existe que pour le client Unity, et il n'est pas
            # decoratif : `JsonUtility` construit TOUJOURS l'objet imbrique,
            # meme absent du JSON. Un bloc manquant y devient donc un bloc a
            # zero, ou `connected` vaut faux — et l'alerte d'isolement se
            # leverait sur tout monde dont le serveur ne dit rien. Un champ que
            # seul le serveur peut mettre a vrai est la seule facon de
            # distinguer « pas raccorde » de « pas de reponse ».
            'owned': True,
            'capital': bool(self.is_capital),
            # Raccorde au reseau imperial : il existe un chemin jusqu'a la
            # capitale, par des lignes ouvertes ou par le voisinage de systeme.
            'connected': self.is_connected,
            # Stabilite a zero : production nulle, chantiers geles. Le monde
            # est eteint, pas encore perdu.
            'deactivated': self.is_deactivated,
            'stability': self.stability_score,
            # Le compte a rebours de la secession. Nul tant que le monde n'est
            # pas tombe a zero — c'est la seule chose qui le declenche.
            'unstable_since': (self.unstable_since.isoformat()
                               if self.unstable_since else None),
            'secedes_at': secedes.isoformat() if secedes else None,
        }

    def build_refusal(self, building_type):
        """
        Pourquoi ce batiment ne peut pas monter d'un niveau, `None` s'il le peut.

        Rend une PHRASE, et dans l'ordre ou l'on peut y remedier : la place
        d'abord — un refus definitif, que rien ne corrigera —, la technologie
        ensuite, les ressources en dernier. La route rendait « prerequis non
        atteint » pour les trois, ce qui envoyait chercher du fer pour une ferme
        qu'aucune plateforme ne portera jamais.
        """
        refusal = self.place_refusal(building_type)
        if refusal is not None:
            return refusal

        missing = self.missing_technologies(building_type)
        if missing:
            return "Cannot build %s. Requires: %s." % (
                building_type.name,
                ", ".join("%s %d" % (name, level)
                          for name, level in sorted(missing.items())))

        building = self.get_building(building_type=building_type)
        if not self.match_prerequisite(building.cost):
            return ("Cannot build %s: not enough resources." % building_type.name)

        return None

    def can_be_increased(self, building_type):
        """
        Check if building can be increase of level
        ---
        :return:
        """
        return self.build_refusal(building_type) is None

    def increase(self, building_type):
        """
        ---
        :return:
        """
        # Un seul endroit sait pourquoi un batiment est refuse — pas de sol,
        # pas d'hydrogene, une technologie ou des ressources manquantes — et
        # c'est `build_refusal`. Le dupliquer ici ferait deux verites.
        refusal = self.build_refusal(building_type)
        if refusal:
            raise ValueError(refusal)

        building = self.get_building(building_type=building_type)
        if building:
            # Paye a la commande, comme le chantier de vaisseaux : c'est le
            # moment ou le joueur a montre qu'il en avait les moyens, et rien
            # ne garantit qu'il les aura encore a la livraison.
            self.spend(building.cost)
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

    def missing_technologies(self, element):
        """
        Les technologies qui manquent pour construire cette unite.
        ---
        `BuildingType`, `ShipType` et `DefenseType` declarent leurs prerequis
        sous `requirements.technologies`. Ils n'etaient lus par personne : le
        nom `laser` qu'ils reclamaient n'existait meme pas dans l'enum des
        technologies. Il existe maintenant, et il est verifie ici — pour une
        coque, une batterie comme pour un batiment.

        :param element: membre de `BuildingType`, `ShipType` ou `DefenseType`
        :return: {nom de technologie: niveau requis}, vide si tout est acquis
        """
        from app.models.game.technologies.technology import Technology

        required = (element.value.get('requirements') or {}).get('technologies') or {}
        if not required or not self.user:
            return {}

        levels = Technology.levels(user=self.user)
        return {
            name: level for name, level in required.items()
            if levels.get(name, 0) < level
        }

    def build(self, type, item, spawn=None):
        """
        Build ships or defenses on the territory.
        ---
        :param spawn: point d'apparition Unity {x, y, z} pour la flotte qui
            recevra les vaisseaux, quand le serveur doit en creer une. Seul le
            client connait la geometrie du systeme ; un client qui n'en a pas
            (la console web) l'omet, et la flotte nait a l'origine du repere.
        """
        shipyard = self.get_building(building_type=BuildingType.shipyard)

        if type == PositionalEventType.ship:
            element = ShipType[item["type"]]
            scope = ModifierScope.Ships
        elif type == PositionalEventType.defense:
            element = DefenseType[item["type"]]
            scope = ModifierScope.Defenses

        # Les prerequis technologiques, verifies pour de bon.
        #
        # `DefenseType` les declare depuis toujours — l'Artillerie laser demande
        # `laser`, la Coilgun `atomique` — mais rien ne les lisait : la console
        # les affichait, le serveur les ignorait, et n'importe qui pouvait
        # assembler une batterie ionique sans avoir rien cherche. C'est ce qui
        # donne son poids a toute la branche Armement.
        #
        # Ce qui est demande est la TECHNOLOGIE, pas un palier dedans : un
        # deblocage tombe au premier niveau, et les suivants n'ajoutent que de
        # la puissance.
        missing = self.missing_technologies(element)
        if missing:
            raise ValueError(
                "Cannot build %s. Requires: %s." % (
                    element.name,
                    ", ".join("%s %d" % (name, level) for name, level in missing.items())))

        # Le cout de la commande, pas celui d'une piece : `element.cost` est
        # unitaire, et la verification le prenait tel quel. Une commande de dix
        # passait donc avec de quoi en payer une seule -- ce que le message
        # d'erreur juste en dessous dementait deja en annoncant la quantite.
        quantity = item["quantity"]
        unit_cost = self.modifiers.apply_cost(element.cost, scope=scope)
        cost = {resource: amount * quantity for resource, amount in unit_cost.items()}
        if not self.match_prerequisite(cost):
            raise ValueError(f"Cannot build {quantity} {element.name}. Prerequisites not reached.")
        self.spend(cost)

        # Meme acceleration que les batiments : ce sont des chantiers du meme
        # territoire, et les separer donnerait une galaxie rapide sur ses
        # batiments et lente sur ses flottes.
        unitary_duration = element.duration(shipyard=shipyard) / GalaxySettings.value(
            self.galaxy_name, 'build_time_divider')
        unitary_duration = self.modifiers.shorten(unitary_duration, scope=scope)
        extra_args = {
            "name": element.name,
            "quantity": item["quantity"],
            "initialQuantity": item["quantity"],
            "unitaryDuration": unitary_duration
        }
        if type == PositionalEventType.ship and spawn is not None:
            extra_args["spawn"] = spawn

        return PositionalEvent.create(
            territory=self,
            user=self.user,
            duration=unitary_duration * item["quantity"],
            event_type=type,
            extra_args=extra_args
        )


    @property
    def energy(self):
        building = self.get_building(building_type=BuildingType.power_station)
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
            # Ce qu'il faudrait pour prendre ce monde, du point de vue de celui
            # qui regarde. C'est le serveur qui tranche : une regle recopiee
            # dans deux clients divergerait au premier equilibrage, et le
            # bouton se dessine a partir d'ici.
            'claim': self.claim_offer(),
            # Ce que ce monde peut porter. Le client s'en sert pour dresser sa
            # liste de batiments : sans lui, il proposerait une ferme sur une
            # plateforme orbitale, que le serveur refuse.
            'construction': self.construction_offer(),
            # Raccordement, extinction, secession — ce qu'il faut pour voir
            # venir la perte d'un monde. Nul pour qui n'en est pas le
            # proprietaire : voir `holding_status`.
            'holding': self.holding_status(),
            # Colonie ou plateforme : le client n'affiche ni les memes chiffres
            # ni les memes boutons pour l'une et pour l'autre.
            'orbital': bool(self.orbital),
            'is_capital': bool(self.is_capital),
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


# Enregistre la table des lignes de commerce aupres des metadonnees. `create_all`
# ne batit que les modeles IMPORTES, et rien n'importe ce module au chargement :
# les lectures ne s'en font qu'a l'interieur de methodes, pour ne pas boucler.
# Sans cette ligne, la table manque partout ou le schema sort de `create_all` —
# c'est-a-dire dans toute la suite de tests. Meme motif que
# `app/models/user.py`, qui enregistre ainsi les jetons d'appareil.
from app.models.game.trade import TradeLine  # noqa: E402,F401
