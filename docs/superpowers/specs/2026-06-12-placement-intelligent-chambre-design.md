# Design — Placement intelligent des équipements électriques (pilote chambre)

**Date :** 2026-06-12
**Statut :** Validé (brainstorming), prêt pour plan d'implémentation
**Périmètre :** Pilote sur la **chambre** uniquement. Le moteur est conçu pour s'étendre pièce par pièce ensuite, sans réécriture.

## 1. Problème

Aujourd'hui les pastilles d'équipements électriques (prises, RJ45, interrupteur, point lumineux) se placent **en tas autour de la pastille de la pièce** (`smart_placement_with_polygon` / `smart_placement_fallback_cluster`). Le résultat est illisible et ne reflète pas la pose réelle d'un artisan.

Cible (logique métier, ex. chambre) :
- deux prises **contre le mur tête-de-lit**, de part et d'autre du lit ;
- une **RJ45 accolée** à l'une de ces deux prises ;
- une **3ᵉ prise sur le mur d'en face**, formant un triangle avec les deux premières ;
- l'**interrupteur sur le mur à côté de la porte** (côté intérieur) ;
- le **point lumineux au centre** de la pièce.

Toutes les briques de données existent déjà mais ne sont pas exploitées pour le placement :
- polygones de pièces (`RoomDetection.polygon`, segmentation Mask2Former) ;
- lignes de murs (`extract_wall_lines` / `extract_lines_from_image` dans `polygon_postprocess.py`) ;
- bboxes mobilier (YOLO brique A : `Bed`, `Toilet`, `Shower`, `WashBasin`, `KitchenSink`…) ;
- bboxes **portes/fenêtres** (modèle YOLO existant `runs/train/v3_doors_windows/weights/best.pt`, classes `{0: door, 1: window}`, mAP50≈0.92) — **présent mais pas encore câblé dans l'app Streamlit**.

## 2. Approche retenue

**Moteur d'« ancres » déclaratif (A) + couche de raffinement (C).**

Pour chaque type de pièce, une **spec déclarative** mappe chaque équipement à une *ancre* géométrique (relative au mobilier, aux murs, à la porte, ou au centre) plus un éventuel offset. Un **résolveur géométrique** déterministe transforme ces ancres en coordonnées pixel à partir des détections. Puis une **couche de raffinement** colle proprement aux murs (`snap_to_wall`) et résout les chevauchements (`resolve_collisions`).

Choisi parce que : explicable et testable règle par règle, colle exactement au raisonnement de l'artisan, et extensible (une nouvelle pièce = une nouvelle spec, pas un nouveau moteur). Alternatives écartées : optimisation par coût/contraintes (boîte noire, overkill pour un pilote 1 pièce).

## 3. Architecture

Nouveau package **pur** (aucun import Streamlit/torch → testable en isolation) :

```
src/planrec/placement/
  contracts.py   # dataclasses d'entrée/sortie normalisées (pixel)
  geometry.py    # primitives géométriques réutilisables
  spec.py        # specs déclaratives par type de pièce (pilote: chambre)
  resolver.py    # moteur : spec + détections → équipements placés
```

### 3.1 Contrats (`contracts.py`)

```python
@dataclass
class Detection:
    cls: str                     # "Bed", "door", "window"…
    bbox: tuple[int,int,int,int] # (x1,y1,x2,y2) pixels
    confidence: float

@dataclass
class RoomContext:
    room_type: str               # "BedRoom"
    polygon: list[tuple[int,int]]
    furniture: list[Detection]   # YOLO brique A
    openings: list[Detection]    # YOLO v3 doors/windows
    wall_lines: list[tuple[int,int,int,int]]  # existants

@dataclass
class PlacedEquipment:
    equip_key: str               # "prise_courant", "interrupteur"…
    x: int; y: int
    confidence: float
    uncertain: bool              # → halo orange dans le canvas
    reason: str                  # "côté gauche du lit" (debug/tooltip)
```

Toutes les coordonnées sont en **pixels image d'origine** (cohérent avec polygones, bboxes YOLO, lignes murs, placement actuel).

### 3.2 Primitives géométriques (`geometry.py`)

Chaque primitive est pure et testable seule :

| Primitive | Rôle |
|-----------|------|
| `room_edges(polygon)` | côtés du polygone → `Edge(seg, orientation, inward_normal)` |
| `wall_behind(bbox, edges)` | mur contre lequel un meuble est plaqué (edge le plus proche / max contact) |
| `opposite_edge(edge, edges)` | mur ~parallèle et en face |
| `edge_of(bbox, edges)` | mur portant une ouverture (porte) |
| `point_on_edge(edge, t, inset)` | point à la fraction `t` du mur, décalé `inset` vers l'intérieur |
| `project_extents(bbox, edge)` | projection d'un meuble sur un mur → `(t_min, t_max)` (« de part et d'autre ») |
| `triangle_apex(p1, p2, edge)` | point sur `edge` formant un triangle équilibré avec `p1,p2` |
| `beside_door(door_bbox, edge, inset)` | point intérieur, côté battant, à côté de la porte |
| `centroid(polygon)` | barycentre pièce |
| `snap_to_wall(p, wall_lines, max_dist)` | raffinement (couche C) → `(x, y, moved)` |
| `resolve_collisions(points, min_gap)` | anti-chevauchement (couche C) |

### 3.3 Spec chambre (`spec.py`)

```python
BEDROOM_SPEC = [
  Rule("prise_courant", anchor=BedSide(LEFT),       wall=WallBehindBed),   # prise #1
  Rule("prise_courant", anchor=BedSide(RIGHT),      wall=WallBehindBed),   # prise #2
  Rule("prise_rj45",    anchor=Adjacent("prise#1"), offset=ACCOLE),        # rj45 collée
  Rule("prise_courant", anchor=TriangleApex(["prise#1","prise#2"]),
                        wall=OppositeWall),                                  # prise #3 en triangle
  Rule("interrupteur",  anchor=BesideDoor,          wall=DoorWall),
  Rule("point_lumineux",anchor=RoomCentroid),
]
```

**Résolution de « de part et d'autre du lit » :** `wall_behind(bed)` donne le mur tête-de-lit ; `project_extents(bed, wall)` donne les deux extrémités du lit projetées sur ce mur ; prise#1/#2 = `point_on_edge` à ces deux `t` (inset ~15px). Prise#3 : `opposite_edge` + `triangle_apex`. Interrupteur : `edge_of(door)` + `beside_door`. Lumière : `centroid`.

### 3.4 Résolveur (`resolver.py`)

`resolver.place(ctx: RoomContext, equipments) -> list[PlacedEquipment]` :
1. charge la spec du `room_type` ;
2. résout chaque règle en coordonnée via les primitives ;
3. applique la couche C (`snap_to_wall` sur prises/interrupteurs, puis `resolve_collisions`) ;
4. renseigne `uncertain` + `reason`.

## 4. Découplage quantité / position

Le **nombre** d'équipements reste piloté par les règles NFC existantes (`nfc_rules.py`). La spec ne fait que **positionner** les instances déjà générées, elle n'en change pas le compte. Si NFC demande une prise supplémentaire (cas handicap : 4 prises au lieu de 3), la règle excédentaire tombe sur une **répartition par défaut** (mur libre, à la manière de l'ancien placement uniforme).

## 5. Dégradation & marquage incertain

Stratégie : **best-effort + marqueur à valider** (jamais de retour silencieux au tas actuel pour les chambres traitées).

- Détection clé absente/sous seuil (lit manquant → plus de `BedSide`) : on retombe sur une répartition uniforme du mur, et on positionne `uncertain=True`.
- Porte absente : interrupteur sur le mur le plus proche de la pastille de pièce, `uncertain=True`.
- Si `snap_to_wall` / `resolve_collisions` a dû déplacer un point de plus d'un seuil (X px), `uncertain=True`.

`reason` documente la décision (tooltip/debug).

## 6. Intégration Streamlit & canvas

**Câblage YOLO portes :** ajout dans `streamlit_app.py` de `load_yolo_doors_model()` + `run_yolo_doors()` (calqués sur la brique A) pointant sur `runs/train/v3_doors_windows/weights/best.pt`. Résultat caché en `session_state`, passé au `RoomContext`, et rendu en overlay visuel comme le mobilier.

**Point de branchement** (`build_smart_placer`) :

```
pour chaque pièce du devis:
   si room_type a une spec (pilote: BedRoom) ET RoomContext exploitable:
        PlacedEquipment[] = resolver.place(RoomContext, equipments)
   sinon:
        smart_placement_with_polygon   ← inchangé (zéro régression hors chambre)
```

Les `x/y` alimentent les `EquipmentInstance` existants comme aujourd'hui.

**Canvas :** `EquipmentInstance` gagne un champ `uncertain` propagé jusqu'à `PastilleCanvas.tsx` → halo orange léger autour de l'icône (réutilise le pattern d'overlay existant). Tout reste draggable. Respecte le pattern de sync existant (React owns mutable state, Python sync add/remove uniquement).

## 7. Tests

Module pur → tests rapides (hors marker `slow`). `tests/test_placement_*.py`.

- **Unitaires primitives** : `wall_behind`, `opposite_edge`, `triangle_apex`, `beside_door`, `project_extents` sur polygones synthétiques (rectangle + forme en L).
- **Golden chambre** : `RoomContext` reconstruit depuis le cas réel (lit à droite, porte en bas) → assert que les 3 prises sont sur les bons murs, RJ45 accolée, interrupteur côté porte, lumière centrée, avec tolérance px.
- **Dégradation** : lit absent → prises réparties + `uncertain=True` ; porte absente → interrupteur près pastille + `uncertain=True`.

Aucune dépendance Streamlit/torch dans ces tests (`RoomContext` = dataclasses pures).

## 8. Hors périmètre (pilote)

- Specs des autres pièces (cuisine, salon, SDB) — viendront en réutilisant le moteur.
- Contraintes de hauteur NFC (interrupteur 1,2 m, prise 0,3 m…) — non spatialisées sur le plan 2D.
- Ré-entraînement / amélioration des modèles de détection (murs, portes, mobilier).
- Câblage des circuits / routage des liaisons entre équipements.
