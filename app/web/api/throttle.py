# -*- coding: utf-8 -*-

"""
Un frein sur les routes que l'on peut marteler.

Deux d'entre elles meritent le nom : l'inscription, qu'un script remplirait de
comptes jusqu'a saturer la base, et la connexion, ou l'on essaie des mots de
passe voles ailleurs par milliers.

Ce que ce frein est, et ce qu'il n'est pas
------------------------------------------
C'est un compteur a fenetre fixe, garde EN MEMOIRE DU PROCESSUS. Il ne survit
pas a un redemarrage, et deux ouvriers gunicorn comptent chacun de leur cote —
avec quatre ouvriers, la limite reelle vaut quatre fois celle qui est ecrite.

Ce n'est donc pas une protection : c'est un ralentisseur. Il transforme « dix
mille essais en une minute » en « quelques centaines », ce qui suffit a rendre
une attaque par dictionnaire inutile contre des mots de passe ranges en scrypt,
et a laisser le temps de s'apercevoir de quelque chose. Une vraie limite
demanderait un compteur partage — Redis, ou la base — et une decision sur ce
qu'on fait quand ce compteur est injoignable. Le jour ou le jeu sera expose,
c'est cette conversation-la qu'il faudra avoir.

Ecrire cela ici plutot que de laisser croire a une barriere : un frein qu'on
prend pour une serrure est pire que pas de frein du tout.
"""

import time

from flask import request


#: Fenetres ouvertes, par (seau, cle). La valeur est (debut, compte).
_counters = {}

#: Au-dela, on vide les fenetres perimees. Sans cela, un serveur de longue duree
#: garderait une entree par adresse vue depuis son demarrage.
_SWEEP_AT = 4096


class TooManyAttempts(Exception):
    """Le seau est plein. Porte le nombre de secondes a attendre."""

    def __init__(self, retry_after):
        super().__init__("Too many attempts. Try again in %d seconds."
                         % max(1, int(retry_after)))
        self.retry_after = max(1, int(retry_after))


def caller():
    """
    De qui vient la requete.

    `X-Forwarded-For` n'est PAS lu : derriere un proxy mal configure — ou sans
    proxy du tout — c'est un en-tete que le client choisit lui-meme, et un
    frein qu'on desamorce en changeant une ligne d'en-tete ne freine rien. Le
    jour ou un proxy de confiance sera devant, il faudra le declarer
    explicitement, pas le deviner.
    """
    return request.remote_addr or 'unknown'


def hit(bucket, key=None, limit=10, window=60):
    """
    Compte un essai. Leve `TooManyAttempts` si le seau deborde.

    :param bucket: le nom de la route freinee.
    :param key: ce qu'on compte — l'adresse d'ou vient la requete par defaut.
    :param limit: essais autorises dans la fenetre.
    :param window: duree de la fenetre, en secondes.
    """
    now = time.time()
    slot = (bucket, key or caller())

    started, count = _counters.get(slot, (now, 0))
    if now - started >= window:
        started, count = now, 0

    count += 1
    _counters[slot] = (started, count)

    if len(_counters) > _SWEEP_AT:
        _sweep(now=now, window=window)

    if count > limit:
        raise TooManyAttempts(retry_after=started + window - now)

    return count


def forget(bucket, key=None):
    """
    Vide un seau.

    Appele apres une connexion REUSSIE : les essais qui precedent une reussite
    ne sont pas une attaque, ce sont des fautes de frappe, et le joueur qui
    vient de trouver son mot de passe n'a aucune raison d'etre bloque au geste
    suivant.
    """
    _counters.pop((bucket, key or caller()), None)


def _sweep(now, window):
    for slot in [s for s, (started, _) in _counters.items()
                 if now - started >= window]:
        _counters.pop(slot, None)


def reset():
    """Vide tout. N'existe que pour que deux tests ne se genent pas."""
    _counters.clear()
