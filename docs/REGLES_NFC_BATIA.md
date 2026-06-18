# Règles batIA — Équipements & Tableau électrique (NF C 15-100)

> Document de référence — état au **2026-06-18** (règles tableau v2).
> Source de vérité : `src/planrec/nfc_rules.py` (équipements par pièce),
> `src/planrec/nfc_tableau.py` (circuits + tableau), `src/planrec/nfc_pricing.py`
> (prix). Ce document synthétise les règles métier réellement implémentées.

## 1. Pipeline en bref

1. **Reconnaissance des pièces** (segmentation + OCR) → catégorie NFC par pièce.
2. **Règles d'équipement par pièce** → quantités (prises, points lumineux, etc.).
3. **Chauffage & garantie lave-linge** → ajouts au niveau pièce / logement.
4. **Devis facturable** → lignes + prix (les appareils spécialisés agrégés en « Alim spé »).
5. **Tableau électrique** → circuits (disjoncteurs) répartis sur les différentiels.

Catégories NFC reconnues : Chambre, WC, Salle de bain, Cuisine, Cellier/Buanderie,
Séjour, Dégagement, Extérieur, Garage.

---

## 2. Équipements par pièce

Quantités générées par pièce (avant chauffage). « +1 handicap » = prise
supplémentaire si l'option Norme handicap est active.

| Pièce | Prises | RJ45 | Points lumineux | Interrupteurs | Spécifique |
|---|---|---|---|---|---|
| **Chambre** (= bureau) | 3 (+1 handicap) | 1 | 1 | 1 | — |
| **Séjour** | 1 / 4 m², **min 5** (3 derrière TV incluses) | 2 | 1 | 1 | — |
| **Cuisine** | **6** prises normales | — | 1 | 1 | + 3 alim spé : Four, Plaque, Lave-vaisselle |
| **Salle de bain** | 1 (+1 handicap) | — | 2 | 1 | Sèche-serviettes si chauffage ; ⚠ zone 60 cm interdite |
| **WC** | 0 (1 si handicap) | — | 1 | 1 | — |
| **Cellier / Buanderie** | 1 | — | 1 | 1 | + 3 alim spé : Lave-linge, Sèche-linge, Cumulus |
| **Dégagement** | 1 | — | 1 | 1 | — |
| **Extérieur** | 1 | — | 1 | 1 | Interrupteur à voyant |
| **Garage** | 1 | — | 1 | 1 | Règles génériques (type cellier minimal) |

Notes :
- **Cuisine** : 6 prises normales + 3 alimentations spécialisées (Four/Plaque/LV)
  affichées et facturées séparément (voir §5). Total points d'utilisation = 9.
- **Séjour** : 1 prise tous les 4 m² (minimum 5), dont au maximum 3 derrière la TV
  (incluses dans le total, pas en sus). Les 2 RJ45 vont au coffret VDI.
- **RJ45** : hors tableau de puissance → coffret VDI séparé (hors V1 batIA).

---

## 3. Chauffage électrique (si option chauffage active)

| Équipement | Pièces concernées | Quantité |
|---|---|---|
| **Convecteur** | Séjour, Chambres | `max(1, arrondi_sup(surface / 20 m²))` si surface connue ; sinon **forfait : Séjour = 2, Chambre = 1** |
| **Sèche-serviettes** | Salle de bain | 1 par SDB |

- Seuil convecteur : **1 par tranche de 20 m²** (≈ 100 W/m², convecteur ~2000 W).
  Ex. séjour 45 m² → 3 ; chambre 11 m² → 1.
- Tant que les surfaces ne sont pas calculées, le forfait par type s'applique.
- Aucun chauffage en cuisine, WC, cellier, dégagement, extérieur, garage.

### VMC, pompe à chaleur, borne véhicule
- **VMC** : auto, **1 par logement**, placée **cellier → SDB** (rien si aucune).
  Circuit 16 A / 1,5 mm², **Type A**. Pastille + ligne « VMC » dédiées.
- **Pompe à chaleur** et **borne de recharge véhicule** : **ajout manuel** (palette),
  32 A / 6 mm², **Type F**. Pastille + ligne dédiées. Non générées automatiquement.

---

## 4. Garanties de placement au niveau logement

### Lave-linge — au moins une alimentation par logement
- Si une pièce porte déjà un lave-linge (cellier détecté) → rien à faire.
- Sinon → rattachement à la **première pièce candidate** : **Salle de bain →
  Cuisine → Garage → Dégagement**.
- Si **aucune** pièce candidate plausible (logement réduit à un WC ou à des
  chambres) → **pas de lave-linge** ajouté (pas d'alimentation fantôme).

### ECS (cumulus / eau chaude sanitaire) — alimentation spécialisée
- Générée dans le **cellier** s'il existe (règle cellier).
- Sinon → **garage** uniquement s'il est **attenant** à la maison, sinon **SDB**.
- Si aucune candidate → pas d'ECS auto.
- L'attribut « garage attenant » est déterminé géométriquement (polygone garage
  partageant un mur avec une pièce intérieure) — *brique séparée, à venir*.

Le lave-linge et l'ECS garantis sont des alimentations spécialisées 20A (§5, §6).

---

## 5. Alimentations spécialisées & chauffage : affichage et facturation

Deux familles d'appareils, traitées différemment :

| Famille | Appareils | Pastille sur le plan | Ligne de devis |
|---|---|---|---|
| **Alimentation spécialisée** | Four, Plaque, Lave-vaisselle, Lave-linge, Sèche-linge, Cumulus | Pastille générique « Alim spé » | **1 ligne « Alimentation spécialisée » agrégée par pièce** (prix unitaire 70 €) |
| **Chauffage** | Convecteur, Sèche-serviettes | Pastille propre (icône dédiée) | Ligne dédiée « Convecteur » / « Sèche-serviettes » |
| **Équipements fixes** | VMC, Pompe à chaleur, Borne véhicule | Pastille propre | Ligne dédiée « VMC » / « Alim pompe à chaleur » / « Alim borne véhicule » |

- Les **types précis** (Four/Plaque/…) restent connus en interne pour
  dimensionner le tableau (ampérage, section, différentiel) — voir §6.
- Sur le **plan**, les 6 appareils s'affichent tous comme la même pastille
  violette « Alim spé » (l'artisan les place / distingue par contexte).
- Au **devis**, les 6 appareils d'une même pièce sont regroupés en **une seule
  ligne « Alimentation spécialisée »** (quantité = nombre d'appareils).
- **Aucun équipement n'est exclu du devis** : tout ce qui est posé est facturé.

---

## 6. Tableau électrique — circuits (disjoncteurs)

Chaque type d'usage produit un ou plusieurs circuits, avec son disjoncteur, sa
section de câble et sa limite de points par circuit.

| Circuit | Disjoncteur | Section câble | Max par circuit | Différentiel |
|---|---|---|---|---|
| **Éclairage** | 10 A | 1,5 mm² | 5 points | **A** |
| **Prises** (générales) | **16 A** | **1,5 mm²** | **8 prises** | AC |
| **Prises cuisine** | **20 A** | **2,5 mm²** | **6 prises** | AC |
| **Four** | 20 A | 2,5 mm² | 1 (circuit dédié) | AC |
| **Plaque de cuisson** | **32 A** | **6 mm²** | 1 (dédié) | **A** |
| **Lave-vaisselle** | 20 A | 2,5 mm² | 1 (dédié) | AC |
| **Lave-linge** | 20 A | 2,5 mm² | 1 (dédié) | **A** |
| **Sèche-linge** | 20 A | 2,5 mm² | 1 (dédié) | AC |
| **Chaudière / Cumulus (ECS)** | 20 A | 2,5 mm² | 1 (dédié) | AC |
| **Convecteur** | 20 A | 2,5 mm² | 2 convecteurs | AC |
| **Sèche-serviettes** | 20 A | 2,5 mm² | 1 (dédié) | AC |
| **VMC** | 16 A | 1,5 mm² | 1 (dédié) | **A** |
| **Pompe à chaleur** | **32 A** | **6 mm²** | 1 (dédié) | **F** |
| **Borne véhicule** | **32 A** | **6 mm²** | 1 (dédié) | **F** |

Règles de regroupement :
- **Éclairage** et **prises générales** : bin-packing — on remplit des circuits
  jusqu'à la limite (5 points / 8 prises), les grandes pièces sont découpées.
- **Prises cuisine** : circuit dédié 20 A / 2,5 mm² (6 max), séparé des prises générales.
- **Appareils spécialisés** : 1 circuit dédié par appareil.
- **Convecteurs** : 2 par circuit maximum.
- **Sèche-serviettes / VMC / PAC / borne** : 1 circuit dédié chacun.

> Note : limites « 8 prises » (16 A / 1,5 mm²) et « 5 points lumineux » selon
> NF C 15-100. Le RJ45 n'est pas dans le tableau de puissance.

---

## 7. Disjoncteurs différentiels (DDR / interrupteurs différentiels)

### 7.1 Sensibilité
**30 mA** pour tous les différentiels (résidentiel).

### 7.2 Nombre minimum de différentiels
`nombre = max( règle typologie , règle surface , arrondi_sup(nb_disjoncteurs / 8) )`

| Critère | Valeur |
|---|---|
| Typologie | T1 → 2 · T2 → 2 · T3 → 3 · T4 → 4 · T5 → 4 |
| Surface | ≤ 35 m² → 1 · ≤ 100 m² → 2 · > 100 m² → 3 |
| Capacité | **8 disjoncteurs maximum par différentiel** |

Minimum réglementaire absolu : **2 différentiels** par logement (même en studio).

### 7.3 Familles de différentiels (Type A / F / AC)
Chaque circuit appartient à une famille selon le type de différentiel requis :

| Type | Circuits |
|---|---|
| **Type A** | Éclairage, VMC, Plaque de cuisson, Lave-linge |
| **Type F** | Pompe à chaleur, Borne véhicule (super-immunisé, fuites HF) |
| **Type AC** | Tout le reste : prises, four, lave-vaisselle, sèche-linge, ECS, convecteurs, sèche-serviettes |

- Au moins **1 différentiel Type A** (l'éclairage est toujours présent).
- **1+ différentiel Type F** uniquement si PAC ou borne installées.

### 7.4 Répartition des circuits
1. Chaque famille (A / F / AC) est placée sur ses propres différentiels.
2. Chaque famille est découpée par paquets de **8 circuits max**.
3. Les circuits **AC** sont **répartis équitablement** (round-robin) sur autant
   de différentiels que nécessaire pour atteindre le minimum réglementaire —
   en zones indépendantes plutôt qu'en différentiels de réserve vides.

### 7.5 Calibre d'un différentiel
`calibre = Σ(ampérages chauffage + ECS) + Σ(ampérages autres usages) / 2`,
arrondi au **calibre normalisé supérieur** parmi **{25, 40, 63, 80, 100, 125} A**.

- « Chauffage + ECS » (comptés plein) = convecteurs, sèche-serviettes, cumulus,
  **pompe à chaleur**.
- « Autres usages » (coefficient de simultanéité 0,5) = prises, éclairage,
  électroménager non-chauffant, VMC, borne véhicule.

---

## 8. Prix indicatifs HT (fourniture + pose, France 2025)

À ajuster par l'utilisateur selon sa grille réelle.

| Équipement | Prix HT |
|---|---|
| Prise de courant | 25 € |
| Prise RJ45 | 40 € |
| Point lumineux | 50 € |
| Interrupteur | 18 € |
| **Alimentation spécialisée** (Four/Plaque/LV/LL/SL/Cumulus) | **70 €** |
| Convecteur (alim) | 65 € |
| Sèche-serviettes (alim) | 70 € |
| VMC | 90 € |
| Alim pompe à chaleur | 150 € |
| Alim borne véhicule | 250 € |

TVA : Neuf 20 % · Rénovation > 2 ans 10 % · Rénovation énergie 5,5 %.

---

## 9. Hors périmètre / points d'attention

- **RJ45 / VDI** : géré hors tableau de puissance (coffret VDI séparé).
- **Surfaces** : le comptage des convecteurs bascule automatiquement sur la
  formule surfacique dès que les surfaces seront calculées de façon fiable.
- **Salle de bain** : zone de 60 cm autour de la douche/baignoire interdite
  (signalée en note).
- Les appareils électroménagers sont **fournis par l'occupant** : batIA facture
  l'**alimentation** (le circuit posé par l'artisan), pas l'appareil.
