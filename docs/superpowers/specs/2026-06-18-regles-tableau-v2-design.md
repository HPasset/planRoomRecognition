# Design — Règles tableau v2 (différentiels A/F/AC, VMC, PAC, borne, prises)

Date : 2026-06-18
Branche : feat/placement-chambre
Spec A d'un lot en 2 parties. **Spec B** (séparée) = détection géométrique
« garage attenant ». A consomme un attribut `attenant` (entrée, défaut `False`).

Périmètre : `src/planrec/nfc_rules.py`, `src/planrec/nfc_tableau.py`,
`src/planrec/nfc_equipments.py`, `src/planrec/nfc_pricing.py`. Pas de géométrie.

## Contexte

Synchro métier avec l'associé électricien (2026-06-18). Six évolutions des
règles NF C 15-100 : élargissement du Type A, introduction du Type F, nouveaux
équipements (VMC, pompe à chaleur, borne de recharge), ajustements prises et
placement de l'ECS.

## Décisions validées

| # | Sujet | Décision |
|---|---|---|
| 1 | Type A | Reçoit : Plaque cuisson, Lave-linge, **Éclairage** (tous circuits), **VMC** |
| 2 | Prises générales | 16A / 1,5 mm² / **8 prises max** (était 5) |
| 3 | Prises cuisine | **6 prises / 20A / 2,5 mm²** (circuit dédié cuisine) |
| 3b | Plaque cuisson | reste **32A / 6 mm² / Type A** (le « 20A » de #3 = Four + LV seulement) |
| 4 | ECS (cumulus) | alim spé ; placement **cellier → garage (si attenant) → SDB** |
| 5 | Pompe à chaleur | nouvel équipement **manuel**, 32A / 6 mm² / **Type F** |
| 6 | Borne véhicule | nouvel équipement **manuel** (placé par l'utilisateur), 32A / 6 mm² / **Type F** |
| — | VMC | nouvel équipement **auto (1/logement)**, 16A / 1,5 mm² / Type A, ligne+pastille dédiées, placement cellier → SDB |
| — | Repli vide | si aucune pièce candidate → pas de placement auto (cohérent garantie lave-linge) |

## 1. Modèle de différentiels (refonte `_distribute_circuits_to_rcds`)

### Attribut circuit
Le dataclass `Circuit` (`nfc_tableau.py`) gagne `requires_type_f: bool = False`
en parallèle de `requires_type_a: bool`. Un circuit appartient à exactement une
famille : Type A (`requires_type_a`), Type F (`requires_type_f`), sinon AC.

| Famille | Circuits (`requires_*`) |
|---|---|
| **Type A** | Plaque cuisson, Lave-linge, tous les circuits Éclairage, VMC |
| **Type F** | Pompe à chaleur, Borne véhicule |
| **Type AC** | Prises (générales + cuisine), Four, Lave-vaisselle, Sèche-linge, ECS/cumulus, Convecteurs, Sèche-serviettes |

### Répartition
`_distribute_circuits_to_rcds(circuits, n_rcds)` :
1. Sépare les circuits en 3 groupes : A, F, AC.
2. Crée des DDR **Type A** pour le groupe A (toujours ≥ 1, l'éclairage est
   toujours présent), des DDR **Type F** pour le groupe F (≥ 1 seulement si
   PAC/borne présents), des DDR **Type AC** pour le groupe AC.
3. Chaque groupe est découpé en paquets de **8 circuits max** (`MAX_BREAKERS_PER_RCD`).
4. Le nombre total de DDR doit être ≥ `n_rcds` (min typologie/surface, inchangé) :
   si la somme des DDR par groupe est inférieure, on ajoute des DDR **AC**
   supplémentaires (vides) jusqu'à atteindre le minimum.
5. Calibre de chaque DDR recalculé par `_compute_rcd_amps` (inchangé), 30 mA.

`RCD.rcd_type` accepte désormais `"A" | "AC" | "F"`.

`_build_lighting_circuits` passe `requires_type_a=True` sur chaque circuit
Éclairage (était `False`).

## 2. Prises

### Générales (toutes pièces sauf cuisine)
16A / 1,5 mm² / **`SOCKET_MAX_PER_CIRCUIT = 8`** (était 5). Builder
`_build_socket_circuits` inchangé hormis la constante.

### Cuisine (cas dédié)
Les prises de la cuisine sont routées vers un circuit dédié **20A / 2,5 mm²**,
max 6 par circuit (`KITCHEN_SOCKET_MAX_PER_CIRCUIT = 6`). Nouveau
`CircuitType.KITCHEN_SOCKET` et builder `_build_kitchen_socket_circuits`.
`generate_tableau` sépare, lors de la collecte, les prises des pièces de
catégorie `Cuisine` (→ liste cuisine) des autres (→ liste générale).

## 3. Cuisine (règles équipement — `nfc_rules.py`)
Inchangé côté quantités (6 prises + Four/Plaque/LV). La plaque garde
32A/6mm²/Type A via `_SPECIALIZED_SPECS` (déjà le cas). Seule la **section/ampérage
des 6 prises cuisine** change (via le routage §2 côté tableau).

## 4. Nouveaux équipements

### Types (`nfc_rules.py` — `EquipmentType`)
`VMC = "vmc"`, `HEAT_PUMP = "pompe_a_chaleur"`, `EV_CHARGER = "borne_vehicule"`.

### Specs circuits (`nfc_tableau.py`)

| Équip. | `CircuitType` | Ampérage | Section | requires_type_a | requires_type_f | Compté chauffage (calibre) |
|---|---|---|---|---|---|---|
| VMC | `VMC` | 16A | 1,5 mm² | **oui** | non | non (×0,5) |
| Pompe à chaleur | `HEAT_PUMP` | 32A | 6 mm² | non | **oui** | **oui** (plein pot) |
| Borne véhicule | `EV_CHARGER` | 32A | 6 mm² | non | **oui** | non (×0,5) |

`_compute_rcd_amps` : ajouter `CircuitType.HEAT_PUMP` à `heat_types`.

**Construction des circuits** : VMC, PAC et Borne sont ajoutés à
`_SPECIALIZED_SPECS` (1 circuit dédié par instance). Le tuple de specs gagne un
champ `requires_type_f` ; `_build_specialized_circuits` pose `requires_type_a`
**et** `requires_type_f` sur le circuit. `generate_tableau` ajoute `VMC`,
`HEAT_PUMP`, `EV_CHARGER` à la boucle qui collecte `spec_rooms` depuis
`devis.items`.

### Génération
- **VMC** : auto, 1 par logement. Fonction `_ensure_vmc(out)` (niveau logement,
  après la boucle pièces) : si une pièce porte déjà VMC → rien ; sinon placement
  **cellier → SDB** ; sinon pas de placement.
- **PAC / Borne** : **manuels** uniquement (ajout depuis la palette). Aucune
  génération auto. Apparaissent dans le tableau dès qu'ils sont présents dans
  `devis.items`.

### Pastilles & devis (`nfc_equipments.py`)
- VMC, PAC, Borne ont **leur propre pastille** (clés `EQUIP_TYPES` `VMC`,
  `HeatPump`, `EVCharger`) et **leur propre ligne de devis** (pas « Alim spé »).
- Les trois sont **disponibles dans la palette manuelle** (hors
  `CANVAS_HIDDEN_EQUIP_KEYS`).
- Icônes : à défaut d'icône dédiée disponible, réutiliser un `svg_id` existant
  proche (ex. `special_feed`) en attendant des assets dédiés — à noter, non
  bloquant.

### Prix (`nfc_pricing.py`, indicatifs, ajustables)
VMC = 90 €, Pompe à chaleur (alim) = 150 €, Borne véhicule (alim) = 250 €.
Libellés FR : « VMC », « Alim pompe à chaleur », « Alim borne véhicule ».

## 5. Garantie ECS (`nfc_rules.py`)
L'ECS (cumulus, type `BOILER`) reste générée dans la pièce cellier (règle
STORAGE inchangée). Nouvelle fonction `_ensure_ecs(out)` (niveau logement) pour
le cas **sans cellier** : si une pièce porte déjà BOILER → rien ; sinon
placement **garage (si la pièce garage a `attenant=True`) → SDB** ; sinon pas
de placement. ECS reste un `SPECIAL_FEED_EQUIPMENT_TYPES` (affiché/facturé en
« Alim spé » générique).

### Attribut `attenant`
- `Devis` gagne `attenant: bool = False`.
- `compute_devis_global` lit `r.get("attenant", False)` par pièce et le pose sur
  le `Devis`.
- `_ensure_ecs` ne retient une pièce garage que si `devis.attenant`.
- Tant que la **Spec B** n'est pas livrée, `attenant` vaut `False` partout →
  repli ECS effectif = cellier → SDB.

## Tests

Différentiels :
1. Logement complet → DDR Type A contient plaque + lave-linge + éclairage + VMC.
2. PAC ou borne présents → ≥ 1 DDR Type F les contenant ; absents → aucun DDR F.
3. > 8 circuits dans un groupe → découpé en plusieurs DDR du même type.
4. Min RCD (typologie/surface) respecté même avec peu de circuits.

Prises :
5. Pièce hors cuisine 8 prises → 1 circuit 16A/1,5mm² ; 9 prises → 2 circuits.
6. Cuisine 6 prises → 1 circuit `KITCHEN_SOCKET` 20A/2,5mm².

Équipements :
7. VMC auto : présente une fois (cellier→SDB) ; ligne « VMC » + pastille propre.
8. PAC/Borne ajoutés → circuit 32A/6mm² Type F, ligne+pastille propres ; absents
   par défaut.
9. PAC comptée plein pot dans le calibre du DDR Type F.

ECS :
10. Sans cellier, garage `attenant=True` → ECS au garage ; `attenant=False` → SDB.
11. Sans cellier ni garage-attenant ni SDB → pas d'ECS auto.

Non-régression :
12. Suite complète verte ; tableau cohérent (calibres, 30 mA).

## Hors scope
- **Spec B** : calcul géométrique de `attenant` (adjacence polygones/murs).
- Assets icônes définitifs VMC/PAC/borne (fallback `special_feed` accepté).
- Ajustement fin des prix (placeholders).

## Addendum 2026-09-07 — règles cabinet (schéma unifilaire + étiquettes)

| # | Sujet | Décision |
|---|---|---|
| A1 | Calibre ID | **63 A max** par interrupteur différentiel ; au-delà, les circuits basculent sur un autre ID de la même famille (`MAX_RCD_AMPS`) |
| A2 | Type A | Plaque, lave-linge, VMC, **prises GTL ×2** (circuit 16 A ajouté systématiquement, absent du catalogue) et **un seul** circuit éclairage ; les autres éclairages sont posés un par ID AC |
| A3 | Éclairage | 5 points par circuit ; une pièce qui dépasse 5 garde **un circuit dédié entier** (salon 6 spots + 1 PL), plus de découpage |
| A4 | Libellés | Codes pièces courts : SEJ, CUIS, CH1…, BUR, BAIN, WC, CEL, DGT, EXT, GAR (« Écl. CH2 CH3 DGT BAIN CEL », « PC SEJ ») ; étiquettes sur 3 lignes en 6 pt, bande Localisation du schéma sans troncature |

Remplace la décision #1 (« Éclairage : tous circuits » en type A).
