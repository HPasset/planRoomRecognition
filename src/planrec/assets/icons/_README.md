# Charte des pictogrammes batIA

Chaque fichier `.svg` de ce dossier respecte les contraintes suivantes :

- `viewBox="0 0 40 40"` (carré 40×40 abstrait, taille réelle adaptable côté consommateur)
- `stroke="currentColor"` sur les éléments tracés (permet le styling dynamique par le parent)
- `stroke-width="2"` pour les lignes principales, `1.5` pour les détails fins
- `stroke-linecap="round"`, `stroke-linejoin="round"`
- `fill="white"` pour les corps fermés, `fill="none"` pour les contours détachés
- Aucune couleur hardcodée (#xxx ou rgb()) dans `stroke`/`fill`
- Pas de `<rect>` de fond explicite : le fond est implicite blanc côté étiquettes PDF, transparent côté canvas

Ces contraintes sont validées par `tests/test_pastille_canvas_icons.py`.

## Catégories

- **Symboles électriques normés (5)** : socket, switch, light, rj45, differential
  Redessinés d'après les conventions NF EN 60617 (standard technique public).
- **Silhouettes d'appareils (9)** : oven, cooktop, dishwasher, washing_machine,
  dryer, boiler, convector, towel_warmer, special_feed
  Dessins génériques custom batIA, sans copie d'un produit commercial spécifique.
