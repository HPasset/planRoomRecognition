# Design — Rendre visibles toutes les alimentations (plan + devis)

Date : 2026-06-16
Branche : feat/placement-chambre
Périmètre : `src/planrec/nfc_rules.py`, `src/planrec/nfc_equipments.py`,
`app/streamlit_app.py`, `app/pages/0_📋_Devis.py`. **Aucune** modification du
tableau électrique (`nfc_tableau.py`) ni du moteur de calcul des circuits.

## Contexte

Aujourd'hui, 8 types d'équipements sont « circuit-only » : ils alimentent le
tableau électrique mais sont **invisibles sur le plan** (masqués via
`CANVAS_HIDDEN_EQUIP_KEYS`, `nfc_equipments.py:76`) **et exclus du devis
facturable** (filtrés via `CIRCUIT_ONLY_EQUIPMENT_TYPES`,
`app/streamlit_app.py:298` + `app/pages/0_📋_Devis.py:52`).

Conséquences observées (retour métier 2026-06-16) :
- En cuisine, `SOCKET = 9` agrège « 6 prises normales + 3 alim spécialisées »
  (`nfc_rules.py`, bloc KITCHEN). Sur le plan, l'artisan ne voit que 9 prises
  identiques : les 3 alimentations spécialisées (Four/Plaque/LV) sont noyées.
- Le lave-linge garanti (travail récent, type `WASHING_MACHINE`) n'apparaît ni
  comme pastille ni comme ligne de devis.
- Le chauffage (Convecteur, Sèche-serviettes) n'apparaît pas non plus → **trou
  dans le devis** : du matériel posé par l'artisan n'est pas facturé.

On veut rendre **tout visible** (plan + devis), en distinguant deux familles
selon la logique métier.

## Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Représentation des appareils | Pastille **générique « Alim spé »** (pas de pastilles typées) |
| Cuisine sur le plan | **6 prises + 3 Alim spé** (les 3 remplacent 3 des 9) |
| Facturation cuisine | **6 Prise + 3 Alim spé** (relabel, pas juste cosmétique) |
| Lave-linge | Pastille + ligne « Alim spé » comme les autres appareils |
| Chauffage | **Pas** une alim spé → pastille + ligne **dédiées** (Convecteur / Sèche-serviettes) |
| Circuit-only | Supprimé : **plus rien n'est exclu** du plan/devis |

## Principe directeur

Les **types précis restent dans `devis.items`** (`OVEN`, `COOKTOP`,
`DISHWASHER`, `WASHING_MACHINE`, `DRYER`, `BOILER`, `CONVECTOR`,
`TOWEL_WARMER`). Le tableau électrique continue de les lire pour calculer
calibres et DDR Type A — **rien n'y change**. On modifie uniquement la
**génération des pastilles** et la **construction des lignes de devis**.

Deux familles :

| Famille | Types | Pastille | Ligne devis | Prix HT |
|---|---|---|---|---|
| **Alim spé** | OVEN, COOKTOP, DISHWASHER, WASHING_MACHINE, DRYER, BOILER | `SpecialFeed` (générique) | « Alimentation spécialisée » agrégée ×N par pièce | 70 € (`SPECIAL_FEED`) |
| **Chauffage** | CONVECTOR, TOWEL_WARMER | leur icône propre | « Convecteur » ×N / « Sèche-serviettes » ×N | 65 € / 70 € (`nfc_pricing`) |

## Changements détaillés

### 1. Ensembles de types (`src/planrec/nfc_rules.py`)

- Ajouter `SPECIAL_FEED_EQUIPMENT_TYPES: frozenset[EquipmentType]` =
  {OVEN, COOKTOP, DISHWASHER, WASHING_MACHINE, DRYER, BOILER}.
- Supprimer `CIRCUIT_ONLY_EQUIPMENT_TYPES` (et tous ses usages). Plus aucun type
  n'est exclu de la facturation. Les imports dans `app/streamlit_app.py:43` et
  `app/pages/0_📋_Devis.py:27` sont mis à jour (import de
  `SPECIAL_FEED_EQUIPMENT_TYPES` à la place).

### 2. Cuisine (`src/planrec/nfc_rules.py`, bloc KITCHEN)

- `devis.items[SOCKET]` : **9 → 6**.
- `OVEN/COOKTOP/DISHWASHER = 1` : inchangés (déjà présents).
- Mettre à jour le commentaire et la note (`devis.notes`) : « 6 prises normales
  (dont 4 au-dessus plan de travail) + 3 alimentations spécialisées
  (Plaque/Four/LV) ».
- `special_feeds_detail` (« Plaque de cuisson (32A) », « Four », « Lave-vaisselle »)
  **conservé** : il fournit le détail sous la ligne générique côté page Devis.

### 3. Pastilles (`src/planrec/nfc_equipments.py`)

- `CANVAS_HIDDEN_EQUIP_KEYS` se réduit aux **6 appareils** (`Oven`, `Cooktop`,
  `Dishwasher`, `WashingMachine`, `Dryer`, `Boiler`). Ils restent hors **palette
  manuelle** (on ne crée pas 6 boutons typés ; la palette garde le bouton
  « Alim spé » existant). `Convector` et `TowelWarmer` **sortent** de l'ensemble
  → disponibles en palette et générés avec leur propre icône.
- `generate_equipments_from_devis_global` : nouvelle règle de génération —
  - si `nfc_type ∈ SPECIAL_FEED_EQUIPMENT_TYPES` → émettre une pastille
    `type="SpecialFeed"` (couleur/icône de `EQUIP_TYPES["SpecialFeed"]`),
    une par unité de quantité ;
  - sinon, comportement actuel (clé via `NFC_TO_EQUIP_TYPE`, skip si la clé est
    dans `CANVAS_HIDDEN_EQUIP_KEYS`).
  Résultat : Four/Plaque/LV/LL/SL/Cumulus → pastilles « Alim spé » ;
  Convecteur/Sèche-serviettes → leurs pastilles propres.

### 4. Facturation (`app/streamlit_app.py` `build_devis_lines_initial` + `app/pages/0_📋_Devis.py`)

- Retirer la branche `if eq in CIRCUIT_ONLY_EQUIPMENT_TYPES: continue`.
- Pour chaque pièce, **agréger** les quantités des 6 types
  `SPECIAL_FEED_EQUIPMENT_TYPES` en **une seule ligne** :
  - Équipement = « Alimentation spécialisée », Qté = somme, Prix HT = 70 €.
- Les autres types (dont CONVECTOR, TOWEL_WARMER) → 1 ligne chacun comme
  aujourd'hui, au libellé/prix de `nfc_pricing` (Convecteur 65 €,
  Sèche-serviettes 70 €).
- Appliquer la même logique aux deux constructeurs de lignes (la page Devis a
  sa propre fonction d'agrégation, `0_📋_Devis.py:43-78`).

### 5. Lave-linge garanti

Le `WASHING_MACHINE` posé par la garantie logement (cf.
`2026-06-16-convecteurs-lave-linge-design.md`) devient automatiquement une
pastille + une ligne « Alim spé » dès qu'il est rattaché à une pièce réelle
(SDB/cuisine/garage/entrée ou cellier).

> **Amendement 2026-06-17 :** la pièce synthétique `__laundry_virtual__` a été
> supprimée. Un logement sans aucune pièce candidate plausible (WC seul,
> chambres seules) ne reçoit plus de lave-linge ni de ligne « Alim spé »
> fantôme.

## Hors scope (YAGNI)

- Aucune modification du tableau électrique ni du calcul des circuits.
- Pas de pastilles typées par appareil (choix générique « Alim spé » validé).
- Pas de refonte du modèle de prix (on réutilise les valeurs `nfc_pricing`
  existantes).

## Tests

Pastilles (`tests/test_nfc_equipments.py`) :
1. Cuisine (SOCKET=6, OVEN/COOKTOP/DISHWASHER=1) → 6 pastilles `Prise` + 3
   pastilles `SpecialFeed`, 0 pastille typée Four/Plaque/LV.
2. Cellier (WASHING_MACHINE/DRYER/BOILER=1) → 3 pastilles `SpecialFeed`.
3. Pièce chauffée (CONVECTOR=2) → 2 pastilles `Convector` (pas `SpecialFeed`).
4. SDB (TOWEL_WARMER=1) → 1 pastille `TowelWarmer`.

Facturation :
5. Cuisine → 1 ligne « Prise de courant » Qté 6 + 1 ligne « Alimentation
   spécialisée » Qté 3 (prix 70 €).
6. Pièce chauffée → 1 ligne « Convecteur » ; SDB → 1 ligne « Sèche-serviettes ».
7. Aucun équipement de `devis.items` n'est absent du devis (plus de trou) —
   hormis quantités nulles.

Cuisine / règles (`tests/test_nfc_rules_evolutions.py` ou existant) :
8. Bloc KITCHEN : `SOCKET == 6` (était 9).

Non-régression :
9. Le tableau électrique est inchangé : `tests/test_nfc_tableau.py` passe sans
   modification (amps, DDR Type A, lave-linge garanti Type A).

Réconciliation de tests existants :
10. `tests/test_nfc_rules_evolutions.py::test_lave_linge_synthetique_est_circuit_only`
    référence `CIRCUIT_ONLY_EQUIPMENT_TYPES` (supprimé) et affirme que le
    lave-linge synthétique n'est pas facturable — premisse désormais inversée
    (il devient une « Alim spé » facturable). Réécrire ce test pour vérifier que
    les items du Devis synthétique sont dans `SPECIAL_FEED_EQUIPMENT_TYPES`
    (donc générés en pastille « Alim spé » et facturés). Vérifier qu'aucun autre
    test ne référence `CIRCUIT_ONLY_EQUIPMENT_TYPES` avant suppression
    (`grep -rn CIRCUIT_ONLY_EQUIPMENT_TYPES`).
