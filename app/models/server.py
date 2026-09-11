# -*- coding: utf-8 -*-

"""
Reglages du serveur, par opposition a ceux d'une galaxie.

Une galaxie est une partie : ses reglages disent a quel rythme elle se joue, et
vivent dans `app/models/game/settings.py`. Ceux-ci portent sur la machine
entiere — qui peut s'inscrire, a quelle vitesse on peut essayer des mots de
passe, combien de temps une cle d'appareil reste valable.

Deux regles ont decide de ce qui figure ici :

  · **Chaque reglage est lu par du code qui existe.** Une case qui ne change
    rien est pire qu'une case absente : elle fait croire a un pouvoir qu'on n'a
    pas. La colonne « lu par » de chaque parametre nomme l'endroit.

  · **Rien de ce qui vit dans les fichiers `.ini` n'est ici.** La cle de
    session, l'adresse de la base, la journalisation : les exposer en ecriture
    depuis une page web mettrait le serveur a la merci d'une faute de frappe, et
    la cle de session a la merci d'un compte d'administrateur vole. Ce qui se
    regle a chaud et ce qui se regle au deploiement sont deux choses.

Les valeurs sont dans une colonne JSON, sur une ligne unique. Ajouter un
parametre est alors une modification de code, sans migration de schema — le meme
choix que pour les reglages de galaxie, et pour la meme raison.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON

from app.application import db
from app.models.base import Base


#: Identifiant de l'unique ligne. Le serveur est un, ses reglages aussi ; une
#: cle primaire fixe evite d'avoir a se demander laquelle des lignes fait foi.
ROW_ID = 1


class Setting(object):
    """
    Un reglage : ce qu'il vaut par defaut, ce qu'il change, et ce qu'il accepte.

    Le libelle et l'explication vivent ici et non dans la console : c'est le
    serveur qui applique le reglage, c'est a lui de dire ce qu'il fait. La
    console construit son formulaire a partir de cette description, bornes
    comprises.
    """

    #: Ce que la console doit dessiner. Redefini par les sous-classes.
    kind = 'text'

    def __init__(self, key, label, description, default, applied_by):
        self.key = key
        self.label = label
        self.description = description
        self.default = default
        #: Ou ce reglage est lu. Affiche a l'administrateur : un reglage dont on
        #: ne sait pas ce qu'il touche ne se change pas sereinement.
        self.applied_by = applied_by

    def clean(self, raw):
        """La valeur utilisable, ou ValueError disant pourquoi elle ne l'est pas."""
        raise NotImplementedError

    @property
    def serialize(self):
        return {
            'key': self.key,
            'kind': self.kind,
            'label': self.label,
            'description': self.description,
            'default': self.default,
            'applied_by': self.applied_by,
        }


class BoolSetting(Setting):
    kind = 'bool'

    def clean(self, raw):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in ('true', '1', 'yes', 'on'):
                return True
            if lowered in ('false', '0', 'no', 'off'):
                return False
        if raw in (0, 1):
            return bool(raw)
        raise ValueError("%s: %r n'est ni vrai ni faux" % (self.key, raw))


class IntSetting(Setting):
    kind = 'int'

    def __init__(self, key, label, description, default, applied_by,
                 minimum, maximum, unit=None):
        super(IntSetting, self).__init__(
            key=key, label=label, description=description,
            default=default, applied_by=applied_by)
        self.minimum = minimum
        self.maximum = maximum
        #: « secondes », « jours » : l'unite ne se devine pas d'un nombre.
        self.unit = unit

    def clean(self, raw):
        try:
            # `int(float(...))` refuserait 10.5 en silence en le ramenant a 10.
            # Un nombre a virgule dans un compteur d'essais est une erreur de
            # saisie, pas une valeur a arrondir.
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError("%s: %r n'est pas un entier" % (self.key, raw))

        if value < self.minimum or value > self.maximum:
            # Les bornes sont refusees et non ramenees : qui tape 100000 s'est
            # trompe de champ, et lui rendre le maximum sans rien dire lui
            # laisserait croire que sa valeur est passee.
            raise ValueError(
                "%s: %d est hors des bornes [%d, %d]"
                % (self.key, value, self.minimum, self.maximum))

        return value

    @property
    def serialize(self):
        data = super(IntSetting, self).serialize
        data.update({'min': self.minimum, 'max': self.maximum, 'unit': self.unit})
        return data


class TextSetting(Setting):
    kind = 'text'

    def __init__(self, key, label, description, default, applied_by, maximum=500):
        super(TextSetting, self).__init__(
            key=key, label=label, description=description,
            default=default, applied_by=applied_by)
        self.maximum = maximum

    def clean(self, raw):
        if raw is None:
            return ''
        if not isinstance(raw, str):
            raise ValueError("%s: %r n'est pas un texte" % (self.key, raw))

        value = raw.strip()
        if len(value) > self.maximum:
            raise ValueError(
                "%s: %d caracteres, le maximum est %d"
                % (self.key, len(value), self.maximum))
        return value

    @property
    def serialize(self):
        data = super(TextSetting, self).serialize
        data.update({'max_length': self.maximum})
        return data


#: Les reglages, dans l'ordre ou la console les presente.
SETTINGS = [
    BoolSetting(
        key='registration_open',
        label='Inscriptions ouvertes',
        description=(
            "Quand c'est ferme, la creation de compte est refusee et la console "
            "cesse de la proposer. Les comptes existants entrent normalement. A "
            "fermer sur un serveur prive, ou le temps de traiter une vague de "
            "comptes automatiques."
        ),
        default=True,
        applied_by='POST /api/users',
    ),
    TextSetting(
        key='announcement',
        label="Message d'accueil",
        description=(
            "Affiche sur l'ecran de connexion de la console, avant toute "
            "authentification. Vide, rien ne s'affiche. C'est la qu'on annonce "
            "une coupure prevue : personne ne lira un message place derriere le "
            "formulaire quand le serveur est justement injoignable."
        ),
        default='',
        applied_by='GET /api/server',
        maximum=500,
    ),
    IntSetting(
        key='login_attempts',
        label='Essais de connexion',
        description=(
            "Tentatives autorisees depuis une meme adresse avant le refus 429. "
            "Une connexion reussie remet le compteur a zero : les essais qui "
            "precedent une reussite sont des fautes de frappe, pas une attaque."
        ),
        default=10, minimum=1, maximum=1000,
        applied_by='POST /api/auth/token',
    ),
    IntSetting(
        key='login_window',
        label='Fenetre de connexion',
        description="Duree sur laquelle les essais de connexion sont comptes.",
        default=300, minimum=10, maximum=86400, unit='secondes',
        applied_by='POST /api/auth/token',
    ),
    IntSetting(
        key='register_attempts',
        label="Essais d'inscription",
        description=(
            "Creations de compte autorisees depuis une meme adresse dans la "
            "fenetre. C'est ce qui empeche un script de remplir la base."
        ),
        default=5, minimum=1, maximum=1000,
        applied_by='POST /api/users',
    ),
    IntSetting(
        key='register_window',
        label="Fenetre d'inscription",
        description="Duree sur laquelle les inscriptions sont comptees.",
        default=600, minimum=10, maximum=86400, unit='secondes',
        applied_by='POST /api/users',
    ),
    IntSetting(
        key='device_token_days',
        label="Duree de vie d'une cle d'appareil",
        description=(
            "Echeance GLISSANTE : chaque usage la repousse d'autant. Un joueur "
            "qui joue ne revoit jamais le formulaire ; une machine abandonnee "
            "cesse d'ouvrir des sessions au bout de ce delai. La baisser ne "
            "raccourcit pas les cles deja emises, elle s'applique au prochain "
            "usage de chacune."
        ),
        default=90, minimum=1, maximum=3650, unit='jours',
        applied_by='app/models/token.py',
    ),
    IntSetting(
        key='max_devices_per_user',
        label='Appareils par compte',
        description=(
            "Au-dela, la plus ancienne cle vivante est fermee. Sans plafond, un "
            "client qui en redemande une a chaque demarrage en accumulerait des "
            "milliers, toutes valables."
        ),
        default=10, minimum=1, maximum=100,
        applied_by='app/models/token.py',
    ),
    IntSetting(
        key='audit_retention_days',
        label="Conservation du journal d'audit",
        description=(
            "Au-dela, les lignes sont effacees au prochain passage. Un journal "
            "sans limite finit par peser plus lourd que la partie ; trop court, "
            "il ne permet plus de remonter a ce qui s'est passe la semaine "
            "derniere."
        ),
        default=30, minimum=1, maximum=3650, unit='jours',
        applied_by='app/models/audit.py',
    ),
]

SETTINGS_BY_KEY = {setting.key: setting for setting in SETTINGS}

DEFAULTS = {setting.key: setting.default for setting in SETTINGS}


class ServerSettings(Base):
    """
    Les reglages poses sur ce serveur, s'il y en a.

    Une seule ligne, et elle n'existe que si quelqu'un a change quelque chose.
    Elle ne retient que ce qui differe du defaut : un serveur sans ligne et un
    serveur remis a zero se comportent exactement pareil.
    """

    __tablename__ = 'server_settings'

    id = Column(Integer, primary_key=True)

    #: Uniquement ce qui a ete change. Voir `effective`.
    overrides = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, overrides=None):
        self.id = ROW_ID
        self.overrides = overrides or {}

    def __repr__(self):
        return '<server_settings>'

    @classmethod
    def row(cls):
        """
        La ligne, ou None.

        Passe par `Session.get`, qui repond depuis l'identity map : les reglages
        sont relus plusieurs fois par requete — le frein les lit, la route les
        lit — et une requete a chaque fois se verrait.
        """
        return db.session.get(cls, ROW_ID)

    @classmethod
    def effective(cls):
        """Tous les reglages, defauts compris."""
        values = dict(DEFAULTS)
        try:
            row = cls.row()
        except Exception:  # noqa: BLE001 - table absente : on tourne sans reglages
            cls._recover()
            return values

        if row and row.overrides:
            for key, value in row.overrides.items():
                if key in SETTINGS_BY_KEY:
                    values[key] = value
        return values

    @classmethod
    def value(cls, key):
        """
        Un reglage, avec son defaut en secours.

        C'est l'appel que font le frein et les jetons : il ne leve JAMAIS. Une
        base sans la table, une transaction cassee, une valeur illisible rendent
        simplement le defaut. Un reglage n'est pas une regle du jeu ; il ne doit
        pas pouvoir empecher quelqu'un de se connecter.
        """
        default = DEFAULTS.get(key)
        try:
            row = cls.row()
        except Exception:  # noqa: BLE001
            cls._recover()
            return default

        if not row or not row.overrides:
            return default

        return row.overrides.get(key, default)

    @classmethod
    def _recover(cls):
        """
        Rend la transaction au propre apres une requete en echec.
        ---
        Sous Postgres, une requete ratee laisse la transaction dans un etat ou
        tout ce qui suit echoue aussi. Sans ce rollback, une table absente ne
        couterait pas un reglage mais la requete entiere.
        """
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def write(cls, wanted):
        """
        Pose des reglages. Rend l'etat complet une fois pose.

        Les cles absentes ne sont pas touchees. Une cle inconnue fait echouer la
        requete entiere, comme du cote des reglages de galaxie : c'est presque
        toujours une faute de frappe, et l'ignorer en silence laisserait croire
        qu'un reglage est passe.

        Une valeur egale au defaut EFFACE le reglage au lieu de l'enregistrer :
        c'est ce qui fait qu'un serveur remis a zero n'a plus de ligne du tout.
        """
        wanted = wanted or {}

        unknown = [key for key in wanted if key not in SETTINGS_BY_KEY]
        if unknown:
            raise ValueError("Reglage inconnu : %s" % ", ".join(sorted(unknown)))

        row = cls.row()
        if row is None:
            row = cls(overrides={})
            db.session.add(row)

        # `dict(...)` et non une modification en place : SQLAlchemy ne voit pas
        # qu'une colonne JSON a change si l'on mute le dictionnaire qu'elle
        # porte, et la ligne repartirait sans etre ecrite.
        overrides = dict(row.overrides or {})

        for key, raw in wanted.items():
            setting = SETTINGS_BY_KEY[key]
            value = setting.clean(raw)
            if value == setting.default:
                overrides.pop(key, None)
            else:
                overrides[key] = value

        row.overrides = overrides
        db.session.flush()

        values = dict(DEFAULTS)
        values.update(overrides)
        return values
