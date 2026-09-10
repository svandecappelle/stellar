# -*- coding: utf-8 -*-

"""
Les decisions cryptographiques de l'application, en un seul endroit.

Trois sujets qui n'en font qu'un : la cle qui signe les sessions, la facon dont
un mot de passe est range, et la facon dont un jeton d'appareil est fabrique.
Les trois se relisent ensemble ou pas du tout — dispersees, elles derivent, et
c'est exactement le genre de derive qu'on ne voit qu'apres une fuite.

Rien ici ne touche a la base ni a Flask : ce sont des fonctions pures, ce qui
permet de les eprouver sans monter d'application.
"""

import hashlib
import os
import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from config.configuration import AppConfig
from logger import get_logger


#: Variable d'environnement qui porte la cle de signature des sessions.
SECRET_KEY_ENV = 'STELLAR_SECRET_KEY'

#: Longueur minimale d'un mot de passe.
#:
#: Huit, et aucune regle de composition. Imposer une majuscule et un chiffre
#: produit `Password1` et rien d'autre ; la longueur est la seule contrainte
#: qui rende reellement une recherche exhaustive plus chere.
MIN_PASSWORD_LENGTH = 8

#: Longueur maximale. Werkzeug ne tronque pas, mais une requete de connexion ne
#: doit pas pouvoir imposer au serveur de hacher un megaoctet.
MAX_PASSWORD_LENGTH = 256

#: Un mot de passe range par l'ancienne version : SHA-256 nu, en hexadecimal.
#:
#: Il n'y avait ni sel ni cout — deux joueurs choisissant le meme mot de passe
#: portaient la meme empreinte, et une carte arc-en-ciel les rendait tous les
#: deux en une seconde. On sait le reconnaitre pour pouvoir le remplacer a la
#: premiere connexion reussie, sans casser un seul compte.
LEGACY_HASH = re.compile(r'^[0-9a-f]{64}$')

#: Facon de hacher un mot de passe, quand la configuration n'en impose pas.
#:
#: `None` laisse werkzeug choisir : en version 3, scrypt regle a environ cent
#: millisecondes par empreinte. C'est ce qu'il faut en production — imperceptible
#: a la connexion, ruineux pour qui essaie un dictionnaire.
#:
#: `[security] password_method` permet d'en imposer une autre. Cela n'existe que
#: pour la suite de tests : quatre cent dix-sept tests qui creent chacun un
#: compte payaient quarante-six secondes de scrypt, et une suite lente est une
#: suite qu'on cesse de lancer — ce qui coute plus cher en securite que le
#: reglage ne rapporte. Le defaut reste le fort : il faut une ligne EXPLICITE
#: dans un fichier de configuration pour l'abaisser, et `test.ini` est deja
#: inutilisable en production, sa base etant un fichier SQLite.
DEFAULT_PASSWORD_METHOD = None

#: Nombre d'octets tires pour un jeton d'appareil. 32 octets, soit 256 bits :
#: hors de portee d'une recherche exhaustive, et court a transporter en base64.
TOKEN_BYTES = 32


def secret_key():
    """
    La cle qui signe les cookies de session.

    Trois sources, dans cet ordre :

      1. la variable d'environnement — c'est la forme qui convient a un
         conteneur, et la seule qui ne laisse pas la cle dans un depot ;
      2. `[security] secret_key` dans le fichier de configuration ;
      3. a defaut, une cle tiree au hasard au demarrage.

    Le repli tire au hasard est deliberement une cle NEUVE a chaque demarrage,
    et non une constante. Une constante ecrite dans le code — c'est ce qui
    existait — permet a quiconque a lu le depot de forger un cookie de session
    pour n'importe quel compte, administrateur compris. Une cle aleatoire, elle,
    ne coute qu'une chose : les sessions ne survivent pas a un redemarrage. Les
    joueurs ne s'en apercoivent pas, leur jeton d'appareil en rouvrant une
    aussitot ; une panne visible et sans danger vaut mieux qu'une porte ouverte
    et silencieuse.

    En production, poser une cle stable reste preferable : sans elle, un
    redemarrage tournant coupe les requetes en vol.
    """
    from_env = os.environ.get(SECRET_KEY_ENV)
    if from_env:
        return from_env

    try:
        if AppConfig.has('security', 'secret_key'):
            configured = AppConfig.get('security', 'secret_key')
            if configured:
                return configured
    except Exception:
        # La configuration n'est pas encore chargee : on retombe sur le hasard,
        # ce qui est le comportement voulu tant qu'on ne sait rien.
        pass

    get_logger().warning(
        "No session secret configured: falling back on a random key. "
        "Sessions will not survive a restart. "
        "Set %s or [security] secret_key to keep them." % SECRET_KEY_ENV)
    return secrets.token_urlsafe(48)


# ── Mots de passe ────────────────────────────────────────────────────────────

class WeakPassword(ValueError):
    """Un mot de passe que le serveur refuse de ranger."""


def check_password_policy(plain):
    """
    Le mot de passe est-il acceptable ? Leve `WeakPassword` sinon.

    La verification est ici et non dans la route : c'est la seule facon qu'elle
    s'applique aussi bien a l'inscription qu'a un futur changement de mot de
    passe, sans etre reecrite deux fois.
    """
    if plain is None or not isinstance(plain, str):
        raise WeakPassword("A password is required.")

    if len(plain) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            "The password must be at least %d characters long."
            % MIN_PASSWORD_LENGTH)

    if len(plain) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(
            "The password must be at most %d characters long."
            % MAX_PASSWORD_LENGTH)

    return True


def hash_password(plain):
    """
    Range un mot de passe.

    Werkzeug 3 emploie scrypt par defaut — une fonction dure en memoire, reglee
    ici a environ cent millisecondes par empreinte. C'est precisement ce qu'on
    veut : imperceptible a la connexion, ruineux pour qui essaie un
    dictionnaire. SHA-256, lui, est concu pour etre rapide, ce qui en fait le
    mauvais outil pour cet usage-la.

    La politique n'est PAS appliquee ici. Ranger un mot de passe est un
    mecanisme ; decider qu'un mot de passe est trop court est une regle
    d'inscription. Les melanger interdirait a un script d'amorcage de poser le
    compte d'administration qu'il pose depuis toujours, et ferait echouer la
    verification la ou personne ne peut la corriger.
    """
    method = password_method()
    if method:
        return generate_password_hash(plain, method=method)
    return generate_password_hash(plain)


def password_method():
    """
    La facon de hacher imposee par la configuration, ou rien.

    Voir `DEFAULT_PASSWORD_METHOD` : sans ligne explicite, werkzeug choisit, et
    ce qu'il choisit est le bon reglage.
    """
    try:
        if AppConfig.has('security', 'password_method'):
            return AppConfig.get('security', 'password_method') or None
    except Exception:
        # Configuration pas encore lue : le defaut, c'est-a-dire le fort.
        pass
    return DEFAULT_PASSWORD_METHOD


def verify_password(stored, plain):
    """
    Ce mot de passe correspond-il a ce qui est range ?

    Accepte les deux formes : celle de werkzeug, et l'ancienne empreinte SHA-256
    nue. Refuser l'ancienne fermerait la porte a tous les comptes existants au
    moment meme ou l'on cherche a les proteger.
    """
    if not stored or not plain:
        return False

    if LEGACY_HASH.match(stored):
        # Comparaison a temps constant : sur une empreinte connue du serveur
        # l'ecart de duree est infime, mais il n'y a aucune raison de l'offrir.
        given = hashlib.sha256(plain.encode('utf-8')).hexdigest()
        return secrets.compare_digest(given, stored)

    try:
        return check_password_hash(stored, plain)
    except Exception:
        # Une empreinte illisible — methode inconnue, champ tronque — vaut un
        # refus, jamais une erreur cinq cents.
        return False


def needs_rehash(stored):
    """
    Faut-il reranger ce mot de passe ?

    Vrai pour l'ancienne forme. C'est ce qui permet la migration sans mot de
    passe perdu : on ne peut pas recalculer une empreinte scrypt depuis une
    empreinte SHA-256, seulement depuis le mot de passe en clair — et le serveur
    ne le tient qu'une fraction de seconde, a la connexion.
    """
    return bool(stored) and bool(LEGACY_HASH.match(stored))


# ── Jetons d'appareil ────────────────────────────────────────────────────────

def new_token():
    """
    Un jeton d'appareil : la valeur remise au client, une seule fois.

    Le serveur ne la garde pas — il n'en range que l'empreinte. Un vol de la
    base ne rend donc pas les jetons utilisables, exactement comme pour les mots
    de passe.
    """
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token):
    """
    L'empreinte sous laquelle un jeton est range.

    SHA-256 nu, et c'est correct ici la ou ca ne l'etait pas pour un mot de
    passe : un jeton fait 256 bits tires au hasard. Il n'y a ni dictionnaire ni
    carte arc-en-ciel contre ca, et le cout d'un scrypt se paierait a chaque
    requete d'ouverture de session pour ne rien ajouter.
    """
    if not token:
        return None
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
