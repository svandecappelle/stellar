---
description: Passe la porte de verification des deux depots
---

Lance la porte de la forge et rends compte du verdict.

```sh
cd ../stellar-forge && python -m forge.gate $ARGUMENTS
```

Rappels :

- sans argument, tout est joue — environ deux minutes et demie ;
- `--quick` s'arrete apres le serveur, la compilation et le contrat ;
- les controles batch exigent que **l'editeur Unity soit ferme**. Unity
  n'accepte qu'une instance et il n'y a aucun contournement : si la porte le
  signale, dis-le simplement, **ne tue jamais l'editeur**.

Si la porte est rouge, ne commite rien : rapporte l'etape en cause et ce
qu'elle a dit.
