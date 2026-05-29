# Design : Équipements électriques sur le plan (Streamlit POC)

**Date** : 2026-05-28
**Auteur** : Hadrien Passet × Claude
**Statut** : Approuvé pour implémentation
**Issue motrice** : Sortie de réunion batIA Touchpoint — MVP validé par les artisans, recherche d'un "effet waow" pour la prochaine démo.

---

## 1. Contexte

La Streamlit POC batIA permet aujourd'hui :
- OCR PaddleOCR → identification des pièces FR
- Custom component React avec drag-drop des **pastilles de pièces** sur le plan
- Génération automatique du **devis quantitatif NF C 15-100** par pièce
- Affichage tabulaire du devis (Pièce | Équipement | Qté | HT | TTC | Total)
- YOLO Brique A (détection meubles) en overlay optionnel
- Segmentation Mask2Former (polygones pièces) en overlay optionnel

**Le manque identifié** : les équipements électriques (prises, interrupteurs, points lumineux, alimentations spécialisées, RJ45) ne sont représentés que dans des lignes de devis — aucune représentation visuelle sur le plan. Pour un électricien artisan, ce langage visuel est manquant.

## 2. Objectifs

### V1 — Périmètre de ce design

1. Afficher chaque équipement individuel comme une **icône style schéma électrotechnique NF EN 60617** sur le plan, à la bonne pièce
2. **Auto-placement initial intelligent** : prises sur les murs si segmentation active, sinon grappe autour du centre de la pièce
3. **Drag-drop manuel libre** pour ajuster la position de chaque équipement
4. **Sync bidirectionnel** plan ↔ devis : ajout/suppression d'équipement sur le plan met à jour le devis et inversement

### V2 — Hors scope (notes pour plus tard)

- Snap-to-walls "intelligent" (auto-aimant aux murs détectés pendant le drag)
- Contraintes NFC strictes (espacement min entre prises, hauteur, etc.)
- Détection auto des portes pour placer l'interrupteur juste à côté
- Export visuel du plan annoté (PDF / PNG haute résolution)

### Non-objectifs explicites

- Ce n'est PAS un éditeur de schéma électrique normalisé. Les icônes sont stylisées NF EN 60617 mais l'app ne génère pas de schéma technique conforme aux normes d'exécution.
- Pas de gestion des circuits / câbles / disjoncteurs côté plan.

## 3. Décisions de design (avec rationale)

Toutes ces décisions ont été validées en brainstorming le 2026-05-28.

| # | Décision | Choix | Rationale |
|---|---|---|---|
| 1 | Périmètre V1 | Auto-placement initial + drag libre (option B) | Effet "waow" sans nécessiter une R&D auto-placement contrainte complexe |
| 2 | Style icônes | Symboles électrotechniques stylisés NF EN 60617 (option D) | Langage métier des artisans → effet waow garanti pour la démo, ré-utilisable Next.js prod |
| 3 | Sync devis ↔ plan | Bidirectionnel complet | Cohérence avec UX drag-drop pastilles existante, plus puissant pour la démo |
| 4 | Auto-placement initial | Smart si segmentation Mask2Former active, fallback grappe sinon | Évite la dépendance dure à la segmentation tout en exploitant son potentiel quand disponible |
| 5 | Ajout équipement | Palette en bas du canvas (5 chips) | Symétrique avec la palette pièces actuelle à droite, intuitive |
| 6 | Suppression équipement | Drag-out du cadre image | Cohérent avec UX existante (pastilles) |
| 7 | Densité visuelle | Icônes 22px, pastille pièce toujours visible | Compromis lisibilité tactile / encombrement ; toggle on/off via sidebar pour démo contrôlée |

## 4. Architecture

### 4.1 Source de vérité

**Le DataFrame devis (`session_state[devis_lines_key]`) reste la source de vérité quantitative.**

Une nouvelle structure `equipments_state` dans `session_state` stocke les **instances individuelles** d'équipements avec leurs positions. Chaque ligne du devis avec `Qté = N` donne lieu à `N` entrées dans `equipments_state` (une par unité).

Une colonne `_equip_ids: list[str]` est ajoutée au DataFrame devis pour matérialiser le lien : chaque ligne devis liste les UUIDs des instances qu'elle représente.

### 4.2 Flux de données

```
[Action "Générer devis"]
  → devis NFC calculé (Cuisine : 6 prises, 1 RJ45, 1 lumière, 1 inter, 1 alim)
  → pour chaque ligne devis : génère N UUIDs (un par unité de Qté)
  → écrit la liste dans la colonne _equip_ids
  → pour chaque UUID : crée un dict {id, type, room, x, y, color}
  → smart_placement_initial(room_id, type, segmentation_polygon) → (x, y)
  → equipments_state = liste de tous ces dicts

[Render canvas]
  → component reçoit en prop equipments=equipments_state
  → render SVG icônes (NF EN 60617 stylisées) à (x, y) en coords image originale
  → palette équipements (5 chips) rendue sous le canvas

[User drag icône sur plan]
  → component pointer events → nouvelle position
  → callback Python → met à jour equipments_state[i].x/y
  → DataFrame devis inchangé (juste position)

[User drag icône hors cadre image]
  → component détecte out-of-bbox → notifie Python avec id à supprimer
  → Python : retire de equipments_state, retire UUID de _equip_ids de la ligne devis
  → si Qté ligne devis devient 0 : ligne reste mais affiche Qté=0
    (cohérent avec l'UX actuelle qui ne supprime pas auto les lignes)

[User drag depuis palette → cadre image]
  → component détecte drop dans bbox + type équipement
  → callback Python avec (type, pos x/y, pièce cible)
  → détermine la pièce cible : zone contenant (x, y) → pastille la + proche
  → ajoute equipments_state.append({id: uuid, type, room, x, y, color})
  → DataFrame devis : Qté += 1 sur la ligne (pièce, équipement) correspondante
    (si pas de ligne existante → ajout nouvelle ligne via mécanisme manual_backup déjà en place)

[User édite Qté dans tableau devis]
  → on_change DataFrame
  → reconcile_equipments(line) :
      - si new_qty > len(_equip_ids) : génère UUIDs manquants + smart_place
      - si new_qty < len(_equip_ids) : supprime surplus depuis la fin
  → equipments_state à jour

[User supprime ligne devis via 🗑️]
  → tous les UUIDs de _equip_ids retirés de equipments_state

[User supprime pastille pièce]
  → toutes les lignes devis dont Pièce = nom_pièce supprimées
  → → équipements correspondants retirés (cohérence)
```

### 4.3 Composants existants impactés

- `app/components/pastille_canvas/__init__.py` : nouveau paramètre `equipments` + `equip_palette`
- `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` : nouveau type SVG overlay équipements + palette en bas + handlers drag
- `app/streamlit_app.py` : génération equipments_state, sync devis ↔ equipments, sidebar toggle "🔌 Afficher les équipements"
- `src/planrec/nfc_equipments.py` (nouveau) : logique smart_placement + reconcile_equipments (testable en pytest pur)

## 5. Modèle de données

### 5.1 `equipments_state` (session_state)

Clé : `f"equipments_state_{img_hash}"`. Valeur : `list[dict]`.

Chaque dict :

```python
{
    "id": "eq_xyz123abc",            # UUID stable, format "eq_<8 hex>"
    "type": "Prise",                  # Prise | RJ45 | LightPoint | Switch | SpecialFeed
    "room": "Cuisine",                # nom de la pièce dans le devis (ex "Chambre 2")
    "x": 350,                         # px en coordonnées image originale
    "y": 220,
    "color": "rgb(255, 112, 67)",     # CSS color du type (table EQUIP_COLORS)
}
```

### 5.2 Mapping types → libellés / couleurs / symbole SVG

Constante `EQUIP_TYPES` dans `src/planrec/nfc_equipments.py` :

```python
EQUIP_TYPES = {
    "Prise":       {"label": "Prise courant", "color": "rgb(255, 112, 67)", "svg_id": "socket"},
    "RJ45":        {"label": "Prise RJ45",    "color": "rgb(38, 166, 154)", "svg_id": "rj45"},
    "LightPoint":  {"label": "Point lumineux","color": "rgb(251, 192, 45)", "svg_id": "light"},
    "Switch":      {"label": "Interrupteur",  "color": "rgb(66, 165, 245)", "svg_id": "switch"},
    "SpecialFeed": {"label": "Alim spé",      "color": "rgb(171, 71, 188)", "svg_id": "specfeed"},
}
```

Mapping inverse `EquipmentType` (du module `nfc_rules`) → clé `EQUIP_TYPES` :

```python
NFC_TO_EQUIP_TYPE = {
    EquipmentType.SOCKET: "Prise",
    EquipmentType.RJ45: "RJ45",
    EquipmentType.LIGHT_POINT: "LightPoint",
    EquipmentType.SWITCH: "Switch",
    EquipmentType.SPECIAL_FEED: "SpecialFeed",
}
```

### 5.3 Extension du DataFrame devis

Colonne ajoutée : `_equip_ids: list[str]`. Une liste d'UUIDs par ligne. Length = Qté de la ligne (invariant maintenu par `reconcile_equipments`).

## 6. Algorithme : smart placement initial

### 6.1 Avec segmentation Mask2Former active

Entrée : polygone de la pièce (liste de points `[[x, y], ...]` en coords image originale), liste d'équipements à placer pour cette pièce, position de la pastille pièce.

Algorithme :

1. **Point lumineux** → placé au **barycentre** du polygone.
2. **Interrupteur** → placé sur le périmètre du polygone, position la plus proche du centre de la pastille pièce (proxy "près de l'entrée de la pièce", car l'OCR du nom de pièce est souvent près de la porte).
3. **Prises** → réparties uniformément sur le périmètre du polygone, offset d'environ 15 px vers l'intérieur du polygone (pour ne pas être sur le mur exactement). Espacement angulaire = 360° / nb_prises depuis le barycentre.
4. **RJ45** → sur le périmètre, à côté de la 1ère prise.
5. **Alim spécialisée** → sur le périmètre, position symétrique opposée à l'interrupteur (proxy "loin de l'entrée").

Les positions sont des `(x, y)` en coords image originale, sauvegardées dans `equipments_state[i].x/y`.

### 6.2 Sans segmentation (fallback grappe)

Entrée : position de la pastille pièce, liste d'équipements.

Algorithme :

1. Tous les équipements placés en grille compacte centrée sur la pastille pièce.
2. Espacement : 30 px horizontal / 30 px vertical.
3. Petit drift aléatoire ±5 px par équipement pour un rendu moins mécanique.
4. Ordre : prises en 1ère ligne, lumière au centre, interrupteur en dernière ligne, etc.

### 6.3 Cas limites

| Cas | Comportement |
|---|---|
| Pièce sans polygone segmentation ET sans pastille (cas extrême) | Fallback : équipements placés au centre de l'image avec offset aléatoire |
| Polygone < 4 points (corrompu) | Fallback grappe |
| Équipement type inconnu (futur ajout) | Ignoré silencieusement avec warning log |

## 7. UI / Layout

### 7.1 Sidebar — Nouveau toggle

Nouvelle section dans la sidebar entre "🛠 Détection meubles YOLO" et "💡 Devis NFC" :

```
🔌 Équipements électriques sur le plan (optionnel)
  [ ] Afficher les équipements sur le plan
       ↓ si coché :
       Toggle "Tout afficher / Filtrer par type" + 5 checkboxes par type
```

Par défaut : décoché (cohérent avec YOLO et segmentation, démo contrôlée).

### 7.2 Canvas — Layout étendu

Structure du custom component après ajout :

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│   IMAGE PLAN                                               │
│   + polygones segmentation (si activé)                     │
│   + bbox YOLO (si activé)                                  │
│   + pastilles pièces                                       │
│   + icônes équipements (NEW, si activé)                    │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  🔌 Palette équipements (NEW)                              │
│  [Prise] [Inter] [Lumière] [Alim spé] [RJ45]               │
└────────────────────────────────────────────────────────────┘
                                              ┌──────────────┐
                                              │ Palette      │
                                              │ pièces (▶)   │
                                              └──────────────┘
```

La palette équipements s'affiche **uniquement si le toggle est activé**.

### 7.3 Icônes SVG (style NF EN 60617 stylisé)

Les 5 symboles, taille 22px par défaut, avec cliquable area étendue à 32×32 (target tactile) :

| Type | Symbole | Couleur |
|---|---|---|
| Prise | Cercle blanc bordé + barre verticale haut | Orange `rgb(255, 112, 67)` |
| Interrupteur | 2 petits cercles reliés par un trait incliné | Bleu `rgb(66, 165, 245)` |
| Point lumineux | Cercle jaune + croix interne | Jaune `rgb(251, 192, 45)` |
| Alim spécialisée | Cercle bordé + barre verticale + 2 traits triangle (flèche) | Violet `rgb(171, 71, 188)` |
| RJ45 | Rectangle stylisé connecteur avec 3 broches | Vert d'eau `rgb(38, 166, 154)` |

SVG paths définis comme constantes JS dans le composant React. Pas de bibliothèque externe — symboles simples, custom.

## 8. Sync devis ↔ plan : tableau de référence

| Action user | Effet sur equipments_state | Effet sur DataFrame devis |
|---|---|---|
| Drag icône sur plan (intra-image) | `x, y` updated | aucun |
| Drag icône hors cadre image | item retiré | UUID retiré de `_equip_ids`, Qté -= 1 |
| Drag depuis palette → cadre image | item ajouté (smart-place à la position du drop) | UUID ajouté à `_equip_ids` de la ligne (pièce, type), Qté += 1 ; si pas de ligne → nouvelle ligne créée via manual_backup |
| Édit Qté dans tableau devis (ex 3 → 5) | `reconcile_equipments` : ajoute 2 nouveaux items (smart-placed) ou retire surplus | colonne `_equip_ids` regénérée |
| Suppr ligne devis (🗑️) | tous les UUIDs de `_equip_ids` retirés | ligne supprimée |
| Suppr pastille pièce (drag-out canvas) | tous les items dont `room == nom_pièce` retirés | toutes les lignes Pièce = nom_pièce supprimées |

## 9. Phases d'implémentation

| Phase | Durée | Livrable | Tests |
|---|---|---|---|
| 1. Module `src/planrec/nfc_equipments.py` | 1j | `EQUIP_TYPES`, `NFC_TO_EQUIP_TYPE`, `generate_equipments_from_devis()`, `smart_placement()`, `reconcile_equipments()`, fonctions pures testables | pytest unitaires (placement, reconciliation, edge cases) |
| 2. Component React : props `equipments` + `equip_palette` + SVG icônes | 1.5j | Icônes affichées (statiques) sur le plan, palette en bas (statique) | smoke test affichage |
| 3. Drag des icônes existantes + sync position | 1j | Drag fluide (pointer events natifs, pattern utilisé pour pastilles pièces), positions remontées à Python via `setComponentValue` | smoke test drag |
| 4. Palette équipements drag-in (palette → plan) + drag-out (plan → outside) | 1.5j | Ajout/suppression sync DataFrame devis | AppTest régression sync |
| 5. Smart placement initial (intégration avec/sans segmentation) | 2j | Heuristique branche : seg active → algo 6.1, sinon algo 6.2 | pytest sur jeu de polygones tests |
| 6. Toggle sidebar + intégration finale + AppTest | 0.5j | Sidebar toggle, AppTest régression complète (38/38 existants + nouveaux pour la sync devis ↔ equipments) | 38+ tests passent |
| **Total** | **~7-8 jours** | Feature complète démo-ready | |

## 10. Risques et mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Performance React avec 50+ icônes draggables sur un grand T5 | Moyenne | React.memo sur chaque chip (pattern déjà utilisé pour les pastilles), pointer events natifs (pas dnd-kit qui re-render plus) |
| Visual clutter quand toutes options activées (seg + YOLO + pastilles + équipements) | Moyenne | Toggle sidebar par feature (chacune indépendante), encourager démo focus 1 ou 2 features à la fois |
| Smart placement "loupe" sur polygones complexes (L-shape, irréguliers) | Moyenne | Logger en cas de polygone exotique, fallback grappe en cas de calcul foireux, itération en V2 |
| Sync DataFrame devis ↔ equipments_state cassée par bug subtil | Moyenne-Haute | Tests AppTest dédiés à la sync (couvrir add/remove/edit/delete), couverture critique |
| Régression sur les 38 tests AppTest existants | Faible-Moyenne | Tester à chaque phase (gate de progression), pattern on_change déjà maîtrisé |

## 11. Tests à prévoir

Nouveaux tests AppTest à ajouter (à compléter dans le plan d'implémentation) :

- E1 : Générer devis → equipments_state contient bien N items pour une ligne Qté=N
- E2 : Édit Qté 3→5 dans devis → 2 nouveaux items créés
- E3 : Édit Qté 5→2 dans devis → 3 items retirés (ceux du dernier au premier)
- E4 : Suppr ligne devis → tous les items de la ligne supprimés
- E5 : Suppr pastille pièce → tous les items de cette pièce supprimés
- E6 : Smart placement sans segmentation → items dans bbox image
- E7 : Toggle équipements OFF/ON → state préservé

Tests unitaires `nfc_equipments.py` :
- `generate_equipments_from_devis()` : retourne bonne liste pour un DevisGlobal donné
- `smart_placement()` : positions sont dans le polygone (si fourni) ou dans la bbox image (fallback)
- `reconcile_equipments()` : add/remove respecte le delta Qté

## 12. Non-fonctionnel

- **Pas de modification de `streamlit_app.py` pour les tests** : continuer le pattern actuel (mocks dans conftest.py)
- **dist/ committé** : pas besoin de npm build pour exécuter l'app
- **Compatibilité Streamlit 1.57+** : pas de feature beta utilisée

## 13. Définition de "done"

- [ ] Toggle "🔌 Afficher les équipements" disponible dans la sidebar
- [ ] À l'activation : icônes NF EN 60617 stylisées affichées sur le plan, smart-placées
- [ ] Drag-drop fonctionne (intra-image = repositionnement, hors-image = suppression)
- [ ] Palette équipements sous canvas, drag-in fonctionnel
- [ ] Modification Qté dans devis met à jour le nombre d'icônes sur le plan
- [ ] Suppression ligne devis ou pastille pièce nettoie les équipements correspondants
- [ ] 38/38 tests AppTest existants passent toujours
- [ ] ≥6 nouveaux tests AppTest passent pour la sync devis ↔ équipements
- [ ] Tests unitaires `nfc_equipments.py` passent
- [ ] dist/ rebuilt et commité
- [ ] Journal du jour mis à jour avec les actions

---

**Prochaine étape** : invoquer le skill `superpowers:writing-plans` pour générer un plan d'implémentation détaillé par phase.
