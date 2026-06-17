# Règles batIA — Équipements & Tableau électrique (NF C 15-100)

> Document de référence — état au **2026-06-17**.
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

---

## 4. Garantie lave-linge (niveau logement)

Tout logement doit comporter **au moins une alimentation lave-linge**.

- Si une pièce porte déjà un lave-linge (cellier détecté) → rien à faire.
- Sinon → rattachement à la **première pièce candidate** selon l'ordre de
  priorité : **Salle de bain → Cuisine → Garage → Dégagement**.
- Si **aucune** pièce candidate plausible n'existe (logement réduit à un WC ou à
  des chambres) → **pas de lave-linge** ajouté (pas d'alimentation fantôme).

Le lave-linge garanti est une alimentation spécialisée 20A (voir §5 et §6).

---

## 5. Alimentations spécialisées & chauffage : affichage et facturation

Deux familles d'appareils, traitées différemment :

| Famille | Appareils | Pastille sur le plan | Ligne de devis |
|---|---|---|---|
| **Alimentation spécialisée** | Four, Plaque, Lave-vaisselle, Lave-linge, Sèche-linge, Cumulus | Pastille générique « Alim spé » | **1 ligne « Alimentation spécialisée » agrégée par pièce** (prix unitaire 70 €) |
| **Chauffage** | Convecteur, Sèche-serviettes | Pastille propre (icône dédiée) | Ligne dédiée « Convecteur » / « Sèche-serviettes » |

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

| Circuit | Disjoncteur | Section câble | Max par circuit | Différentiel Type A imposé |
|---|---|---|---|---|
| **Éclairage** | 10 A | 1,5 mm² | 5 points | non |
| **Prises** | **16 A** | **1,5 mm²** | **5 prises** | non |
| **Four** | 20 A | 2,5 mm² | 1 (circuit dédié) | non |
| **Plaque de cuisson** | **32 A** | **6 mm²** | 1 (dédié) | **oui** |
| **Lave-vaisselle** | 20 A | 2,5 mm² | 1 (dédié) | non |
| **Lave-linge** | 20 A | 2,5 mm² | 1 (dédié) | **oui** |
| **Sèche-linge** | 20 A | 2,5 mm² | 1 (dédié) | non |
| **Chaudière / Cumulus** | 20 A | 2,5 mm² | 1 (dédié) | non |
| **Convecteur** | 20 A | 2,5 mm² | 2 convecteurs | non |
| **Sèche-serviettes** | 20 A | 2,5 mm² | 1 (dédié) | non |

Règles de regroupement :
- **Éclairage** et **prises** : bin-packing — on remplit des circuits jusqu'à la
  limite (5), les grandes pièces sont découpées en plusieurs circuits.
- **Appareils spécialisés** : 1 circuit dédié par appareil.
- **Convecteurs** : 2 par circuit maximum.
- **Sèche-serviettes** : 1 circuit dédié par salle de bain.

> Note : les limites « 5 prises » et « 5 points lumineux » suivent la NF C 15-100
> pour le 1,5 mm² (16 A). Le RJ45 n'est pas dans le tableau de puissance.

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

### 7.3 Type A vs Type AC
- Le **1er différentiel est de Type A** et reçoit **tous les circuits qui exigent
  le Type A** : **Plaque de cuisson** et **Lave-linge**.
- Les différentiels suivants sont de **Type AC** et reçoivent le reste.

### 7.4 Répartition des circuits (bin-packing)
1. Les circuits Type A obligatoires → différentiel n°1 (Type A).
2. Les autres circuits sont triés par ampérage décroissant et placés sur le
   différentiel **le moins chargé** (max 8 circuits par DDR).
3. Si tous les différentiels sont saturés → on ajoute un différentiel AC.

### 7.5 Calibre d'un différentiel
`calibre = Σ(ampérages chauffage + ECS) + Σ(ampérages autres usages) / 2`,
arrondi au **calibre normalisé supérieur** parmi **{25, 40, 63, 80, 100, 125} A**.

- « Chauffage + ECS » (comptés plein) = convecteurs, sèche-serviettes, cumulus.
- « Autres usages » (coefficient de simultanéité 0,5) = prises, éclairage,
  électroménager non-chauffant.

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
