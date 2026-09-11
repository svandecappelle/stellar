# -*- coding: utf-8 -*-

"""
Le journal d'audit : qui a demande quoi, et ce que le serveur a repondu.

A quoi il sert
--------------
A repondre a « ce joueur a-t-il triche ». Un tricheur ne laisse pas de trace
dans les tables de jeu : elles ne portent que l'etat final, pas le chemin qui y
mene. Ce qui le trahit, c'est la SUITE des demandes — trente constructions en
dix secondes, une flotte lancee vers un systeme qu'on n'a jamais vu, quarante
refus d'affilee sur une route qu'un client normal n'appelle qu'apres avoir
verifie.

D'ou les deux ecritures :

  · **Les gestes notables**, poses a la main aux points de decision. Ils disent
    ce qui a reussi.

  · **Tous les refus**, poses automatiquement par un `after_request`. Ce sont
    eux qui comptent. Un client honnete se fait rarement refuser : il n'envoie
    que ce que l'interface lui permet. Une rafale de 400 et de 403 est le signe
    que quelqu'un parle a l'API directement — ce qui est permis, mais se
    remarque.

Ce qui n'y entre jamais
-----------------------
**Aucun secret.** Pas de mot de passe, pas de valeur de jeton, meme sur un refus
— surtout sur un refus, ou le corps de la requete contient justement le mot de
passe essaye. Un journal d'audit est lu par des administrateurs ; en faire un
depot de mots de passe en clair serait echanger un probleme contre un pire. Le
filtrage est fait par `scrub`, et la liste des cles interdites est volontairement
large.

Ce qu'il coute
--------------
Une insertion par refus, et une par geste notable. C'est peu au regard d'une
requete de jeu, qui en fait plusieurs. Le journal est purge au-dela de
`audit_retention_days` — sans limite, il finirait par peser plus lourd que la
partie.
"""

from datetime import datetime, timedelta
import json

from flask import request
from flask_login import current_user
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.application import db
from app.models.base import Base
from logger import logger


#: Longueur d'un resume. Au-dela, on tronque : une ligne de journal se lit dans
#: un tableau, et une charge utile de dix kilo-octets n'y est pas lisible.
MAX_DETAILS = 2000

#: Ce qui n'est jamais ecrit, quelle que soit la route. Compare en minuscules et
#: par INCLUSION : « password », « new_password » et « passwordConfirm » tombent
#: tous les trois. Large a dessein — rater une cle coute un secret en base,
#: masquer une cle anodine ne coute rien.
SECRET_KEYS = (
    'password', 'token', 'secret', 'digest', 'authorization',
    'cookie', 'session', 'csrf', 'key',
)

#: Ce qui remplace une valeur masquee.
HIDDEN = '***'

#: Routes dont les refus n'apprennent rien. `/api/auth/session` refuse a chaque
#: demarrage d'un client dont la cle a expire — c'est le fonctionnement normal,
#: pas une tentative, et le journal se remplirait de ces lignes-la.
QUIET_REFUSALS = ()


class AuditLog(Base):
    """Une ligne de journal. Immuable : rien ne la modifie apres l'insertion."""

    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    #: Nul pour une demande anonyme — une tentative de connexion ratee en est
    #: une, et c'est precisement celle qu'on veut voir.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    #: Recopie plutot que jointe. Un compte peut disparaitre ; la trace de ce
    #: qu'il a fait doit lui survivre, sinon le journal s'efface avec le
    #: coupable. C'est aussi le nom ESSAYE lors d'une connexion ratee, qui ne
    #: correspond a aucun compte.
    username = Column(String(64), nullable=True)

    #: Le geste, en notation pointee : `auth.login`, `territory.claim`. Un
    #: vocabulaire ferme, declare dans `Action` plus bas.
    action = Column(String(64), nullable=False)

    #: 'ok' ou 'refused'.
    outcome = Column(String(16), nullable=False)

    #: Le code HTTP rendu, quand il y en a un.
    status = Column(Integer, nullable=True)

    #: « POST /api/auth/token ». La route, pas l'URL complete : les parametres
    #: de requete peuvent porter n'importe quoi.
    route = Column(String(255), nullable=True)

    #: D'ou venait la demande. `X-Forwarded-For` n'est pas lu — voir
    #: `app/web/api/throttle.py` pour pourquoi.
    address = Column(String(64), nullable=True)

    #: Le reste, en JSON : identifiants d'objets, quantites, raison du refus.
    #: Filtre par `scrub`.
    details = Column(String, nullable=True)

    __table_args__ = (
        # Le journal se lit presque toujours du plus recent : sans cet index,
        # chaque ouverture de la vue trierait la table entiere.
        Index('ix_audit_log_created_at', 'created_at'),
        # « tout ce qu'a fait ce joueur » est la question qui suit toujours la
        # premiere.
        Index('ix_audit_log_user_id', 'user_id'),
        Index('ix_audit_log_action', 'action'),
    )

    def __repr__(self):
        return '<AuditLog {} {} {}>'.format(self.id, self.action, self.outcome)

    @property
    def serialize(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat(),
            'user_id': self.user_id,
            'username': self.username,
            'action': self.action,
            'outcome': self.outcome,
            'status': self.status,
            'route': self.route,
            'address': self.address,
            'details': json.loads(self.details) if self.details else None,
        }


class Action(object):
    """
    Le vocabulaire du journal.

    Ferme a dessein : une chaine libre a chaque appel donnerait `auth.login`,
    `login`, `user.login` et `auth.signin` pour le meme geste, et le filtre de
    la vue d'administration ne servirait plus a rien.
    """

    REGISTER = 'auth.register'
    LOGIN = 'auth.login'
    LOGOUT = 'auth.logout'
    TOKEN_ISSUE = 'auth.token.issue'
    TOKEN_REVOKE = 'auth.token.revoke'
    SESSION_OPEN = 'auth.session.open'

    TERRITORY_CLAIM = 'territory.claim'
    TERRITORY_BUILD = 'territory.build'
    RESEARCH_START = 'research.start'
    RESEARCH_CANCEL = 'research.cancel'
    FLEET_CREATE = 'fleet.create'
    FLEET_MOVE = 'fleet.move'

    TRADE_OPEN = 'trade.open'
    TRADE_FLOWS = 'trade.flows'
    TRADE_CLOSE = 'trade.close'
    TERRITORY_SECEDE = 'territory.secede'

    GALAXY_CREATE = 'galaxy.create'
    GALAXY_SETTINGS = 'galaxy.settings'

    ADMIN_SETTINGS = 'admin.settings'
    ADMIN_PURGE = 'admin.purge'

    #: Ce que pose l'`after_request` quand rien de plus precis n'a ete note.
    REFUSED = 'api.refused'

    @classmethod
    def all(cls):
        """Les gestes connus, pour le filtre de la vue d'administration."""
        return sorted(
            value for name, value in vars(cls).items()
            if not name.startswith('_') and isinstance(value, str)
        )


OK = 'ok'
REFUSED = 'refused'


def scrub(payload):
    """
    Ce qu'on peut ecrire d'une charge utile.

    Recursif : un mot de passe niche sous une cle anodine doit tomber aussi. Les
    listes sont parcourues, parce qu'un envoi groupe met les objets dedans.
    """
    if isinstance(payload, dict):
        clean = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in SECRET_KEYS):
                clean[key] = HIDDEN
            else:
                clean[key] = scrub(value)
        return clean

    if isinstance(payload, (list, tuple)):
        # Dix elements suffisent a comprendre ce qui a ete demande ; un envoi de
        # mille systemes remplirait la ligne sans rien apprendre de plus.
        trimmed = [scrub(item) for item in list(payload)[:10]]
        if len(payload) > 10:
            trimmed.append('… %d de plus' % (len(payload) - 10))
        return trimmed

    return payload


def caller():
    """
    Qui demande, si on le sait.
    ---
    :return: (user_id, username). Les deux nuls pour une demande anonyme.
    """
    try:
        if not current_user.is_authenticated:
            return None, None
        # `current_user` porte le NOM ; l'objet complet demande une requete, que
        # l'on evite quand la ligne n'a besoin que de l'identifiant.
        user = current_user.get()
        if user is None:
            return None, getattr(current_user, 'id', None)
        return user.id, user.username
    except Exception:  # noqa: BLE001 - hors contexte de requete, par exemple
        return None, None


def record(action, outcome=OK, status=None, username=None, user_id=None, **details):
    """
    Ecrit une ligne de journal.

    **Ne leve jamais.** Une ligne d'audit qui ferait echouer la requete qu'elle
    observe serait un defaut bien pire que l'absence de journal : le joueur
    perdrait son geste parce que la trace n'a pas pu s'ecrire.

    N'appelle pas `commit` : la ligne part avec la transaction de la requete, et
    une reussite journalisee sur une action annulee serait un mensonge.
    """
    try:
        known_id, known_name = caller()

        row = AuditLog(
            user_id=user_id if user_id is not None else known_id,
            username=(username or known_name or None),
            action=action,
            outcome=outcome,
            status=status,
            route=_route(),
            address=_address(),
            details=_pack(details),
        )
        db.session.add(row)
        return row
    except Exception as error:  # noqa: BLE001
        logger.warn("Could not write the audit line",
                    infos=dict(action=action, error=str(error)))
        return None


def refusal(status, action=Action.REFUSED, **details):
    """Un refus, forme courante de `record`."""
    return record(action=action, outcome=REFUSED, status=status, **details)


def prune(days, now=None):
    """
    Efface les lignes plus vieilles que `days`.

    :return: le nombre de lignes effacees.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=max(1, int(days)))

    removed = (
        db.session.query(AuditLog)
        .filter(AuditLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    return removed or 0


def _pack(details):
    if not details:
        return None
    try:
        text = json.dumps(scrub(details), default=str, sort_keys=True)
    except Exception:  # noqa: BLE001
        return None

    return text[:MAX_DETAILS] if len(text) > MAX_DETAILS else text


def _route():
    try:
        # `request.path` et non `request.url` : la chaine de requete peut porter
        # n'importe quoi, y compris ce qu'on refuse d'ecrire ailleurs.
        return '%s %s' % (request.method, request.path)
    except Exception:  # noqa: BLE001
        return None


def _address():
    try:
        return request.remote_addr
    except Exception:  # noqa: BLE001
        return None
