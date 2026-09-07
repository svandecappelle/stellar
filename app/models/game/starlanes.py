# -*- coding: utf-8 -*-

"""
Les liaisons entre etoiles, et les routes qu'elles permettent.

Une flotte ne traverse pas le vide en ligne droite : elle suit les liaisons
tracees entre systemes voisins, saut par saut. C'est ce qui donne un relief a la
carte — un systeme peut etre un passage oblige, un detour peut couter cher — et
c'est ce que le joueur voit deja, puisque ces liaisons sont dessinees sous ses
yeux dans la vue galaxie.

D'ou le point delicat : ces liaisons naissaient cote client. `StarNeighbourhood`
et la boucle de `GalaxyFactory` les calculent a partir des positions des
etoiles, et le serveur n'en savait rien. Un serveur qui inventerait ses propres
liaisons ferait voyager les flottes par des chemins que la carte ne montre pas.

La regle est donc reproduite ici a l'identique, avec les memes constantes :

  · chaque etoile est reliee a ses cinq plus proches voisines dans un rayon de
    six unites ;
  · le rayon s'elargit d'une unite tant qu'il n'en a pas trouve deux, sans
    jamais depasser la diagonale de la galaxie — sans cette borne, une galaxie
    d'une seule etoile bouclerait indefiniment ;
  · les liaisons sont ensuite tenues pour reciproques, comme les traits que
    dessine le client.

Les positions ne changent jamais apres la generation : le graphe est donc
calcule une fois par galaxie et garde en memoire. Le cache retient les couples
(identifiant, position) qui l'ont produit — un systeme ajoute, deplace ou
supprime le refait de lui-meme. Comparer cette liste coute un parcours ; la
reconstruire coute un carre.
"""

import heapq
import math

# Les memes valeurs que `Generator.LinkSearchRadius`, `LinksPerStar` et
# `MinLinksPerStar` cote Unity. Elles vont par paire avec celles-la : les
# changer d'un cote seulement ferait voyager les flottes hors des traits
# dessines sur la carte.
LINK_SEARCH_RADIUS = 6.0
LINKS_PER_STAR = 5
MIN_LINKS_PER_STAR = 2

#: Le pas d'elargissement, quand une etoile est trop isolee pour ses deux
#: voisines. `StarNeighbourhood.Nearest` ajoute une unite a chaque tour.
RADIUS_STEP = 1.0

#: Graphes deja calcules, par galaxie. Voir la note sur le cache en tete.
_cache = {}


def _coordinates(system):
    """
    Les coordonnees d'un systeme, en trois flottants.
    ---
    La colonne est une chaine « x_y_z » : c'est le format que le generateur
    ecrit et que `System.serialize` relit. Un systeme sans position — il ne
    devrait pas y en avoir — est place a l'origine plutot que de faire echouer
    le calcul de toute la galaxie.
    """
    if not system.position:
        return (0.0, 0.0, 0.0)

    parts = system.position.split("_")
    if len(parts) < 3:
        return (0.0, 0.0, 0.0)

    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except (TypeError, ValueError):
        return (0.0, 0.0, 0.0)


def _distance(a, b):
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _diagonal(points):
    """
    La diagonale de la boite qui contient la galaxie.
    ---
    Borne de l'elargissement, exactement comme `StarNeighbourhood.maxRadius` :
    au-dela, il n'y a plus rien a trouver.
    """
    if not points:
        return LINK_SEARCH_RADIUS

    lows = [min(p[axis] for p in points) for axis in range(3)]
    highs = [max(p[axis] for p in points) for axis in range(3)]
    return _distance(tuple(lows), tuple(highs)) + LINK_SEARCH_RADIUS


def _build(systems):
    """
    Le graphe des liaisons, a partir des systemes d'une galaxie.
    ---
    Rend un dictionnaire {id: {id voisin: distance}}, reciproque.
    """
    points = {system.id: _coordinates(system) for system in systems}
    ids = sorted(points)
    limit = _diagonal(list(points.values()))

    lanes = {system_id: {} for system_id in ids}

    for system_id in ids:
        origin = points[system_id]

        # Les distances aux autres, une fois pour toutes : la boucle
        # d'elargissement ne fait que remonter son seuil.
        others = sorted(
            ((_distance(origin, points[other]), other)
             for other in ids if other != system_id),
            key=lambda pair: (pair[0], pair[1]))

        radius = LINK_SEARCH_RADIUS
        while True:
            within = [pair for pair in others if pair[0] <= radius]
            if len(within) >= MIN_LINKS_PER_STAR or radius >= limit:
                break
            radius += RADIUS_STEP

        for distance, other in within[:LINKS_PER_STAR]:
            # Reciproque : le client trace un trait entre deux etoiles des que
            # l'une reconnait l'autre pour voisine, et une flotte emprunte le
            # trait dans les deux sens.
            lanes[system_id][other] = distance
            lanes[other][system_id] = distance

    return lanes


def lanes_of(galaxy_name):
    """
    Le graphe des liaisons d'une galaxie, calcule au premier appel.
    """
    from app.models.game.system import System

    systems = System.all_of(galaxy_name=galaxy_name)
    signature = tuple((system.id, system.position) for system in systems)

    cached = _cache.get(galaxy_name)
    if cached is not None and cached[0] == signature:
        return cached[1]

    lanes = _build(systems)
    _cache[galaxy_name] = (signature, lanes)
    return lanes


def forget(galaxy_name=None):
    """
    Oublie un graphe garde en memoire.
    ---
    Le cache se controle deja tout seul, en comparant les positions qui l'ont
    produit : ceci n'existe que pour le liberer, ou pour repartir de zero dans
    un test qui veut mesurer le calcul lui-meme.
    """
    if galaxy_name is None:
        _cache.clear()
    else:
        _cache.pop(galaxy_name, None)


def neighbours(galaxy_name, system_id):
    """Les systemes joignables en un saut, avec leur distance."""
    return dict(lanes_of(galaxy_name).get(system_id, {}))


def route(galaxy_name, origin_id, destination_id):
    """
    Le chemin le plus court d'un systeme a un autre, en identifiants.
    ---
    Dijkstra sur les distances : le plus court en unites de carte, donc le plus
    rapide, puisque la vitesse ne depend pas du trajet. Rend None quand aucune
    suite de liaisons ne relie les deux — une galaxie peut avoir des amas
    isoles, et c'est au joueur qu'il faut le dire.

    Le chemin rendu commence par `origin_id` et finit par `destination_id`.
    """
    lanes = lanes_of(galaxy_name)

    if origin_id not in lanes or destination_id not in lanes:
        return None

    if origin_id == destination_id:
        return [origin_id]

    best = {origin_id: 0.0}
    previous = {}
    seen = set()
    queue = [(0.0, origin_id)]

    while queue:
        cost, current = heapq.heappop(queue)
        if current in seen:
            continue
        seen.add(current)

        if current == destination_id:
            break

        for other, step in lanes.get(current, {}).items():
            if other in seen:
                continue
            candidate = cost + step
            if candidate < best.get(other, float('inf')):
                best[other] = candidate
                previous[other] = current
                heapq.heappush(queue, (candidate, other))

    if destination_id not in best:
        return None

    path = [destination_id]
    while path[-1] != origin_id:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def edges(galaxy_name):
    """
    Les liaisons d'une galaxie, chacune une seule fois.
    ---
    Le graphe interne est reciproque : chaque liaison y figure deux fois, une
    par extremite. Pour la dessiner il en faut une seule, sans quoi chaque trait
    est trace deux fois — invisible a l'oeil, mais deux fois le poids sur le
    reseau et deux fois le travail au rendu.

    Rend des triplets (plus petit identifiant, plus grand, longueur).
    """
    lanes = lanes_of(galaxy_name)
    seen = set()
    result = []

    for origin, others in lanes.items():
        for other, length in others.items():
            key = (origin, other) if origin < other else (other, origin)
            if key in seen:
                continue
            seen.add(key)
            result.append((key[0], key[1], length))

    result.sort()
    return result


def leg_lengths(galaxy_name, path):
    """
    La longueur de chaque saut d'un chemin, en unites de carte.
    ---
    Separee de `route` parce qu'un ordre donne en cours de route reprend un
    chemin deja calcule et n'a besoin que de ses longueurs.
    """
    lanes = lanes_of(galaxy_name)
    lengths = []
    for index in range(len(path) - 1):
        start, end = path[index], path[index + 1]
        lengths.append(lanes.get(start, {}).get(end, 0.0))
    return lengths
