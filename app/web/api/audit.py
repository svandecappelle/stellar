# -*- coding: utf-8 -*-

"""
L'ecriture automatique du journal d'audit : tous les refus de l'API.

Pourquoi les refus, et pas les reussites
----------------------------------------
Journaliser chaque appel reussi remplirait la table de bruit : une partie
normale en fait des milliers par heure, et aucun ne dit rien. Les gestes qui
meritent une trace en reussite sont poses a la main, un par un, la ou ils se
decident.

Les refus, eux, valent tous la peine. Un client honnete se fait rarement
refuser : il n'envoie que ce que l'interface lui permet, apres avoir verifie ce
qu'il pouvait. Une rafale de 400 et de 403 est le signe que quelqu'un parle a
l'API directement — ce qui n'est pas interdit, mais se remarque, et c'est
exactement ce qu'un administrateur veut pouvoir constater.

Le piege de l'ecriture dans un `after_request`
-----------------------------------------------
Une requete refusee peut avoir deja pose des objets dans la session — un
batiment ajoute avant que la verification de cout ne leve. Valider la
transaction pour y glisser la ligne d'audit ECRIRAIT ces objets-la : le serveur
aurait refuse la construction et l'aurait enregistree quand meme.

D'ou l'ordre : on annule d'abord, on ecrit ensuite. L'annulation est de toute
facon la bonne semantique — une demande refusee ne doit rien laisser — et elle
ne coute rien a une requete qui avait deja valide sa transaction.
"""

from flask import request

from app.application import app, db
from app.models.audit import Action, QUIET_REFUSALS, record, REFUSED


@app.after_request
def audit_refusals(response):
    """
    Note tout refus de l'API.

    Ne leve jamais : une trace qui casserait la reponse qu'elle observe serait
    un defaut bien pire que l'absence de trace.
    """
    try:
        if not _worth_recording(response):
            return response

        # Voir l'en-tete du module : annuler AVANT d'ecrire, sinon la validation
        # qui enregistre la ligne d'audit enregistre aussi ce que la requete
        # refusee avait commence a poser.
        db.session.rollback()

        record(
            action=Action.REFUSED,
            outcome=REFUSED,
            status=response.status_code,
            payload=_payload(),
        )
        db.session.commit()
    except Exception:  # noqa: BLE001 - jamais au detriment de la reponse
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass

    return response


def _worth_recording(response):
    if response.status_code < 400:
        return False

    path = request.path or ''
    if not path.startswith('/api/'):
        # Une icone manquante ou une route inconnue du site ne dit rien de ce
        # qu'un joueur a tente.
        return False

    if path in QUIET_REFUSALS:
        return False

    return True


def _payload():
    """
    Ce que la demande portait, une fois les secrets retires.

    `record` passe tout par `scrub` : les mots de passe et les jetons n'arrivent
    donc jamais en base, y compris — et surtout — sur un refus de connexion, ou
    le corps contient justement le mot de passe essaye.
    """
    try:
        body = request.get_json(silent=True)
    except Exception:  # noqa: BLE001
        body = None

    data = {}
    if isinstance(body, dict) and body:
        data['body'] = body
    if request.args:
        data['query'] = dict(request.args)

    return data or None
