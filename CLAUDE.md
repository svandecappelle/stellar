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

## La console (`app/static`)

HTML, CSS et modules ES servis tels quels — **aucune étape de construction**,
rien à installer. `app/web/ui.py` sert `index.html` pour tous les chemins du
routeur client ; le reste est `api.js` (accès), `icons.js` (pictogrammes et
billes de planète), `systemview.js` (la règle de la descente) et `app.js`.

**La carte de la galaxie est la vue d'accueil**, et un système y **pousse sur
place** quand on descend assez : ses anneaux, ses mondes, et de quoi commander
dessus sans quitter la carte. Il n'y a donc plus « la carte » d'un côté et « la
fiche d'un monde » de l'autre — c'est une seule vue, et la fiche pleine page
n'est qu'un raccourci.

### Ce qui s'y casse, et qu'on ne voit qu'en jouant

**Tout est une fonction de l'AGRANDISSEMENT, rien n'est déclenché.** Le
dépliage, l'effacement de la galaxie, les mondes peints, la place des flottes :
cinq lectures du même cadrage, recalculées ensemble. Un état déclenché se rate
quand la molette dévale, et l'on se retrouve avec des anneaux sans système.

**Une fraction d'écran doit dire de QUELLE dimension elle est la fraction.**
Les seuils de `systemview.js` sont des fractions du **petit côté** : un système
est rond, c'est le côté le plus court qui le coupe. Calés sur la largeur d'un
cadre en 16/10, ils faisaient sortir les deux anneaux extérieurs par le haut et
par le bas — et ce qu'on voit alors n'est pas un système qui déborde, ce sont
des mondes qui manquent.

**Cette carte est un SCHÉMA, pas une scène.** Étoiles, planètes, flottes gardent
une taille d'**écran** constante ; seules les **distances** portent
l'agrandissement. C'est l'écartement des anneaux qui dit qu'on descend, jamais
la grosseur des billes — faire grandir les corps rouvrirait toute la famille de
pièges d'échelle que le client Unity a payée.

**Les orbites ne sont pas stockées par le serveur.** Il donne un rang, et le
client en tire une distance : `1600 + rang × 400`, la même formule que
`SystemOrbits` côté Unity. Deux formules finiraient par dessiner deux systèmes
du même rang. Quand `characteristics.position` existe, elle l'emporte.

**L'épingle.** Zoomer garde le point sous le pointeur immobile — c'est ce qu'on
veut d'une molette — mais un système qui occupe les quatre cinquièmes du cadre
entre alors coupé d'un côté. La descente le recadre donc **jusqu'à ce que le
joueur déplace la vue lui-même**, et non jusqu'à un seuil : un écart pas encore
rattrapé se figerait au seuil, puis serait amplifié par la fin de la descente.

**Une ligne de construction n'est écrite qu'une fois.** `renderBuildings`,
`renderUnits` et `renderFleets` prennent leur monde en argument, et servent
trois vues — la fiche d'une planète, la vue d'empire, le quai de la carte. Trois
copies auraient divergé au premier équilibrage : c'est là que se décide ce qu'un
coût inatteignable donne à voir, et cette question n'a pas trois réponses. Même
raison pour `refreshAfterOrder`, point unique qui repeint **là où l'ordre a été
donné**.

**Lire les territoires d'un système les fait tous avancer** (la production est
créditée à la lecture). Le dépliage en coûte donc un par système visité — d'où
le cache par système, et d'où le `/update` réservé au seul monde ouvert.

La règle risquée vit dans `systemview.js`, **pure et sans DOM**, épinglée par
`tests/unit/system_view.py` — qui l'éprouve avec `node` et se saute s'il manque.

### Prouver qu'un écran marche

Les tests pytest ne touchent que l'API : ils ne diraient rien d'un écran cassé.
Playwright le dit en deux minutes, et c'est ce qui attrape les vraies
régressions — un `pageerror`, une `console.error`.

La recette : un `config/<nom>.ini` jetable (copie de `config/test.ini` dont
`uri` pointe un fichier SQLite), un script qui fait `create_app(<nom>)`, sème une
galaxie et un joueur, puis `app.run(port=…)`. **Rendre `db.session` à `None`
avant `app.run`** — sinon les lectures parallèles d'un écran se marchent dessus
et rendent des 500 qui n'existent pas en production (voir `app/database.py`).
Supprimer le `.ini` à la fin : il n'a rien à faire dans le dépôt.

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
