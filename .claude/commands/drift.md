---
description: Verifie le contrat entre le serveur et le client
---

```sh
cd ../stellar-forge && python -m forge.contract $ARGUMENTS
```

`JsonUtility` apparie par nom de champ **en silence** : un champ que le serveur
rend et que le client ne declare pas est jete, un champ que le client declare
et que le serveur ne rend pas reste a zero. Rien n'echoue, rien n'est
journalise.

Le verdict ne porte que sur ce qui est NEUF. Devant un ecart neuf :

1. dis lequel, et de quel cote il penche ;
2. cherche la cause — un champ renomme cote serveur, une classe oubliee cote
   client ;
3. **ne fige pas la reference pour faire taire l'outil.** `--baseline` sans
   avoir compris est exactement le geste qui le rend inutile.
