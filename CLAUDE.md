# Stellar — serveur Flask

Flask + SQLAlchemy. Ce fichier tient le savoir qui, sans lui, se re-découvre à
chaque session.

## Vérifier

```sh
python -m pytest -q          # ~50 s, 689 tests
```

Et depuis `../stellar-forge`, la porte qui couvre les **deux** dépôts :

```sh
python -m forge.gate --quick   # cette suite + la compilation du client
python -m forge.gate           # tout
```

Une règle changée ici casse le client en silence : voir « Le contrat avec le
client » plus bas.

## Les règles du jeu, telles qu'elles sont vraiment

Ce sont celles qu'on redécouvre le plus souvent, et celles qu'un écran mal
conçu trahit.

**Il n'y a pas de tour.** La production est créditée **au prorata, en continu** :
`Territory.update_view()` rattrape le temps écoulé depuis la dernière lecture
(`_credit_production(since, until)`). Tout écran qui annoncerait une « horloge de
tour » mentirait — le joueur attendrait un moment qui n'arrive jamais.

**Les mondes sont rattrapés à la LECTURE.** Sérialiser un territoire le fait
avancer. C'est pourquoi une route de lecture peut être coûteuse, et pourquoi
`is_connected` prend soin de ne rien écrire (`no_autoflush` : une requête au
milieu du tour déclenche un flush, qui écrit `updated_at` — le jalon même depuis
lequel le temps est compté).

**La chaîne qui tue un monde**, appliquée depuis toujours :

```
coupé du réseau → stabilité −1/h → éteint à 0 → sécession à +3 jours
```

`holding_status()` la rend, **au seul propriétaire** : dire d'un monde ennemi
qu'il est isolé publierait la carte de son réseau. Le drapeau `owned` distingue
« pas raccordé » de « pas de réponse ».

**Le blocus est un robinet, pas une démolition.** Une ligne bloquée reste
*ouverte* et ne raccorde plus rien. Aucune fiche de monde ne dit par qui il est
coupé — seul `/api/trade` le sait.

**Le commerce** demande un Depot aux deux bouts et consomme un Freighter en
orbite de la destination. La **colonisation** demande un ColonyShip — ou une
ExtractionPlatform pour un corps sans sol — sauf pour le premier monde d'une
galaxie.

## Le contrat avec le client

Le client Unity lit ces réponses avec `JsonUtility`, qui **apparie par nom de
champ, en silence**. Un champ renommé ici laisse le champ client à zéro sans un
mot, et le défaut ne se voit qu'en jouant.

Deux garde-fous, et ils ne servent que si on les tient à jour :

* les **échantillons** que lisent les contrôles batch du client, générés ici :

  ```sh
  FIXTURE_OUT=.../Stellar-Unity/Tests python -m pytest tests/api/game/_dump_fixtures.py -s
  ```

  Générateur, pas test : sans `FIXTURE_OUT` il ne s'exécute pas, et il ne
  vérifie rien que la suite ne vérifie déjà. **Relance-le après tout changement
  de forme d'une réponse** — `python -m forge.fixtures` dit si tu as oublié.

* `app/web/api/openapi.generated.json`, régénéré avec la suite.

## Pièges éprouvés

**`@serialize` et les listes.** Le décorateur refusait une liste de
dictionnaires alors que sa propre boucle la traitait — un 500 sans explication.

**`request.json` rend 415 sur un POST sans corps.** Utilise
`request.get_json(silent=True)` dès qu'un corps est facultatif.

**La session `scoped` est rendue au bout de chaque requête.** Ce qui n'a pas été
`commit` part avec elle : en test la session survit et l'écriture paraît posée,
en production elle est perdue. Le journal d'audit, qui annule sur refus, révèle
ces oublis.

**`create_all` masque les migrations.** Le conteneur bâtit les tables neuves au
démarrage, donc `alembic_version` reste en retard : la première migration non
additive cassera.

**Les dates sont des `utcnow()` sans fuseau.** Le client doit les lire en UTC
explicitement, sinon un compte à rebours dérive du décalage horaire — sur une
décision qui coûte un monde.

## Modération

`admin` a une portée `*`, un `moderator` la galaxie qu'il modère
(`User.moderates(galaxy)`). `Territory.grant()` est une porte **à part**, pas un
`build()` complaisant : sans coût, sans délai, sans prérequis, mais elle garde
le seul refus qu'aucune faveur ne lève — la **place** — et ne descend jamais
sous zéro. Chaque geste passe au journal (`moderation.grant`) : un pouvoir sans
trace est un pouvoir qu'on ne peut pas rendre.

## Écrire

Le code et les commits de ce dépôt sont **en français**, et les commentaires
disent *pourquoi*, pas *quoi* — souvent en nommant le défaut que le code
corrige. Garde cette densité.
