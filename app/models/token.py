# -*- coding: utf-8 -*-

"""
Le jeton d'appareil : ce qui evite de redemander un mot de passe.

Un joueur se connecte une fois avec ses identifiants ; le serveur lui remet une
chaine tiree au hasard, que le client range sur sa machine et represente au
demarrage suivant pour rouvrir une session. Le mot de passe, lui, ne quitte
jamais le formulaire.

Trois proprietes decident de sa forme, et aucune n'est negociable :

  · **Le serveur n'en garde que l'empreinte.** Un vol de la base ne rend pas les
    jetons utilisables, exactement comme pour les mots de passe. La valeur
    remise au client n'existe qu'une fois, dans la reponse qui la cree — elle
    n'est plus jamais relisible ensuite, ni par le joueur ni par le serveur.

  · **Il est revocable.** Une ligne par appareil, qu'on peut effacer : c'est ce
    qui permet « deconnecter cette machine », et c'est ce qu'un cookie « se
    souvenir de moi » ne sait pas faire. Un cookie de memorisation reste valable
    tant qu'il n'a pas expire, meme si l'on change de mot de passe.

  · **Il expire.** Une echeance glissante : chaque usage la repousse. Un joueur
    qui joue ne se voit jamais redemander son mot de passe ; une machine dont on
    s'est separe cesse d'ouvrir des sessions au bout de quelques mois, sans que
    personne ait eu a y penser.

Il ne remplace PAS la session : il l'ouvre. Toutes les routes du jeu continuent
de s'authentifier par la session de Flask-Login — un jeton ne circule qu'a
l'ouverture, ce qui reduit d'autant le nombre de requetes qui le transportent.
"""

from datetime import datetime, timedelta

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Index)
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.security import new_token, token_digest
from logger import logger


#: Duree de vie d'un jeton, en jours, repoussee a chaque usage.
#:
#: Quatre-vingt-dix jours : assez long pour qu'un joueur regulier ne revoie
#: jamais le formulaire, assez court pour qu'une machine abandonnee cesse d'etre
#: une porte ouverte avant qu'on ne s'en souvienne.
LIFETIME_DAYS = 90

#: Jetons vivants au plus par compte.
#:
#: Sans plafond, un client qui redemande un jeton a chaque demarrage — parce
#: qu'il l'a mal range, parce qu'il tourne dans un conteneur jetable — en
#: accumulerait des milliers, tous valables. Au-dela, le plus ancien part.
MAX_PER_USER = 10

#: Longueur d'un libelle d'appareil. Ce qui l'affiche est une liste, pas une
#: page : au-dela, on tronque.
MAX_LABEL = 120


class DeviceToken(Base):
    __tablename__ = 'user_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    #: L'empreinte SHA-256 du jeton, en hexadecimal. Jamais le jeton lui-meme.
    digest = Column(String(64), nullable=False, unique=True)

    #: Ce que le joueur lira dans la liste de ses appareils : « Windows · PC du
    #: salon ». Pose par le client, jamais devine par le serveur.
    label = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    #: Date de revocation. Une ligne revoquee est GARDEE : elle dit au joueur
    #: qu'un appareil a ete deconnecte, et a quel moment. Effacer la ligne
    #: effacerait aussi cette trace.
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="tokens")

    __table_args__ = (
        Index('ix_user_tokens_digest', 'digest', unique=True),
        Index('ix_user_tokens_user_id', 'user_id'),
    )

    def __repr__(self):
        return '<DeviceToken {} of {}>'.format(self.id, self.user_id)

    # ── Etat ────────────────────────────────────────────────────────────────

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    def is_expired(self, now=None):
        return self.expires_at <= (now or datetime.utcnow())

    def is_usable(self, now=None):
        return not self.is_revoked and not self.is_expired(now)

    # ── Fabrication ─────────────────────────────────────────────────────────

    @classmethod
    def issue(cls, user, label=None, now=None):
        """
        Remet un jeton neuf a un appareil.

        :return: (la valeur en clair, la ligne). La valeur n'est rendue qu'ici :
            elle n'est nulle part en base, et l'appelant est le seul et dernier
            a la voir passer.
        """
        now = now or datetime.utcnow()
        plain = new_token()

        token = cls(
            user_id=user.id,
            digest=token_digest(plain),
            label=(label or '')[:MAX_LABEL] or None,
            created_at=now,
            expires_at=now + timedelta(days=LIFETIME_DAYS),
        )
        db.session.add(token)
        db.session.flush()

        cls._trim(user=user, now=now)

        logger.info("Device token issued",
                    infos=dict(user_id=user.id, token_id=token.id))
        return plain, token

    @classmethod
    def _trim(cls, user, now):
        """
        Ne garde que les `MAX_PER_USER` jetons vivants les plus recents.
        ---
        Les revoques et les perimes ne comptent pas : ils n'ouvrent plus rien.
        """
        alive = [
            token for token in cls.of(user=user)
            if token.is_usable(now)
        ]
        if len(alive) <= MAX_PER_USER:
            return

        alive.sort(key=lambda t: t.created_at)
        for token in alive[:len(alive) - MAX_PER_USER]:
            token.revoked_at = now
            logger.info(
                "Device token dropped, too many on the account",
                infos=dict(user_id=user.id, token_id=token.id))

    # ── Lecture ─────────────────────────────────────────────────────────────

    @classmethod
    def of(cls, user):
        """Tous les jetons d'un compte, revoques et perimes compris."""
        return db.session.query(cls).filter(cls.user_id == user.id).all()

    @classmethod
    def alive(cls, user, now=None):
        """Les jetons qui ouvrent encore une session, du plus recemment vu."""
        now = now or datetime.utcnow()
        found = [t for t in cls.of(user=user) if t.is_usable(now)]
        found.sort(key=lambda t: t.last_used_at or t.created_at, reverse=True)
        return found

    @classmethod
    def resolve(cls, plain, now=None):
        """
        Le jeton correspondant a cette valeur, s'il ouvre encore quelque chose.

        La recherche se fait sur l'empreinte : c'est la seule chose que le
        serveur connaisse. Rend `None` pour un jeton inconnu, revoque ou perime
        — les trois cas se traitent pareil du point de vue de l'appelant, et les
        distinguer dans la reponse renseignerait qui essaie des valeurs.
        """
        digest = token_digest(plain)
        if not digest:
            return None

        token = db.session.query(cls).filter(cls.digest == digest).first()
        if token is None or not token.is_usable(now):
            return None

        return token

    def touch(self, now=None):
        """
        Note l'usage et repousse l'echeance.
        ---
        C'est ce qui fait de la duree de vie une echeance GLISSANTE : un joueur
        qui joue ne revoit jamais le formulaire, une machine oubliee s'eteint
        toute seule. L'appelant valide la session.
        """
        now = now or datetime.utcnow()
        self.last_used_at = now
        self.expires_at = now + timedelta(days=LIFETIME_DAYS)
        return self

    # ── Revocation ──────────────────────────────────────────────────────────

    def revoke(self, now=None):
        """Ferme ce jeton. Sans effet s'il l'etait deja."""
        if self.revoked_at is None:
            self.revoked_at = now or datetime.utcnow()
            logger.info(
                "Device token revoked",
                infos=dict(user_id=self.user_id, token_id=self.id))
        return self

    @classmethod
    def revoke_all(cls, user, now=None):
        """
        Ferme tous les jetons d'un compte.
        ---
        C'est ce qu'on appelle apres un changement de mot de passe : l'interet
        de changer de mot de passe est de fermer la porte a qui l'avait, et la
        laisser ouverte sur les appareils deja enregistres la laisserait ouverte
        tout court.
        """
        now = now or datetime.utcnow()
        closed = 0
        for token in cls.of(user=user):
            if token.is_usable(now):
                token.revoke(now)
                closed += 1
        return closed

    # ── Publication ─────────────────────────────────────────────────────────

    @property
    def serialize(self):
        """
        Ce qu'un joueur voit de ses appareils.
        ---
        Ni l'empreinte ni le jeton : la premiere ne lui apprend rien et n'a rien
        a faire sur un reseau, le second n'existe plus.
        """
        return {
            'id': self.id,
            'label': self.label,
            'created_at': self.created_at.isoformat(),
            'last_used_at': (
                self.last_used_at.isoformat() if self.last_used_at else None),
            'expires_at': self.expires_at.isoformat(),
            'revoked': self.is_revoked,
        }
