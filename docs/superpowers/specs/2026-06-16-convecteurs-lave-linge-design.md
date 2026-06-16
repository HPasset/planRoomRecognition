# Design — Garantie lave-linge + comptage des convecteurs (NFC 15-100)

Date : 2026-06-16
Branche : feat/placement-chambre
Périmètre : `src/planrec/nfc_rules.py` (couche règles métier devis). Aucune
modification du tableau électrique ni du rendu.

## Contexte

Deux évolutions des règles d'équipement par pièce, demandées suite à
observation métier :

1. **Aucune alimentation lave-linge n'apparaît dans les devis/tableaux.** Le
   lave-linge n'est généré aujourd'hui que dans une pièce de catégorie
   `STORAGE` (Cellier/Buanderie) — `nfc_rules.py:170-180`. La segmentation
   détecte rarement un cellier → aucun circuit `LAUNDRY` créé → pas de DDR
   Type A déclenché par le lave-linge. On veut **garantir au moins un
   lave-linge par logement**.

2. **Le comptage des convecteurs est à plat : 1 par séjour et 1 par chambre**,
   indépendamment de la surface (`nfc_rules.py:230-232`). Un séjour de 40 m²
   reçoit le même unique convecteur qu'une chambre de 9 m². On veut une règle
   proportionnée à la surface, avec un repli réaliste tant que les surfaces ne
   sont pas calculées.

> **Amendement 2026-06-17 :** la pièce synthétique `__laundry_virtual__` a été
> **supprimée**. Si aucune pièce candidate plausible n'existe (logement réduit à
> un WC ou à des chambres), la garantie ne s'applique plus — pas de lave-linge
> fantôme. Voir [2026-06-16-alim-spe-visibles-design.md](2026-06-16-alim-spe-visibles-design.md).

## Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Garantie lave-linge | Niveau logement, **au moins 1**, sans doublon |
| Rattachement si pas de cellier | Pièce de repli par priorité : BATH → KITCHEN → GARAGE → ENTRY |
| Si aucune pièce candidate | ~~Devis synthétique~~ → **rien** (amendement 2026-06-17) |
| Ampérage lave-linge | **20A** (cohérent avec le circuit réel `nfc_tableau.py:273`) |
| Base comptage convecteurs | Surface : `max(1, ceil(surface / 20))` |
| Repli si surface inconnue | Forfait par type : **Séjour = 2, Chambre = 1** |
| Sèche-serviettes | **Inchangé** (1 par SDB si `heating_enabled`) |
| Sèche-linge / cumulus | **Inchangé** (cellier-only) |

## Feature 1 — Garantie « au moins 1 lave-linge par logement »

### Emplacement

Dans `compute_devis_global` (`nfc_rules.py:283`), **après** la boucle qui
calcule les devis par pièce. C'est le seul niveau ayant la visibilité sur
toutes les pièces. `compute_devis_for_room` reste inchangé. Logique isolée dans
une fonction dédiée `_ensure_washing_machine(out: DevisGlobal) -> None`.

### Algorithme

```
si une pièce a déjà items[WASHING_MACHINE] >= 1 :
    return  # garantie déjà satisfaite (cellier détecté), pas de doublon

# chercher une pièce de repli par ordre de priorité
pour cat in [BATH, KITCHEN, GARAGE, ENTRY] :
    si une pièce de cette catégorie existe (la première rencontrée) :
        room.items[WASHING_MACHINE] = 1
        room.special_feeds_detail.append("Lave-linge (20A)")
        return

# aucune pièce candidate → circuit-only
out.per_room.append(Devis(
    room_id="__laundry_virtual__",
    nfc_category=NFCCategory.STORAGE,
    items={WASHING_MACHINE: 1},
    special_feeds_detail=["Lave-linge (20A)"],
))
```

STORAGE n'est jamais candidat de repli : s'il existe il a déjà déclenché un
lave-linge, donc la garantie est satisfaite avant d'arriver à la recherche.

### Impacts aval (aucune modification de code requise)

- **Tableau** : `generate_tableau` lit `WASHING_MACHINE` depuis `devis.items`
  par pièce (`nfc_tableau.py:435-443`) → le circuit `LAUNDRY` 20A Type A est
  créé automatiquement, forçant un DDR Type A même sans cellier.
- **Pastille** : pièce de repli réelle → pastille posée dans cette pièce ;
  cas synthétique `__laundry_virtual__` → `room_id` sans polygone détecté →
  pas de pastille (placement manuel artisan), conforme au choix circuit-only.

### Cohérence du libellé

Le feed existant du cellier affiche « Lave-linge (16A) » (`nfc_rules.py:179`)
alors que le circuit réel est 20A. On corrige cet existant en « Lave-linge
(20A) » pour cohérence avec le nouveau feed et le circuit.

## Feature 2 — Comptage des convecteurs par pièce

### Règle

Remplacer le forfait fixe `CONVECTOR = 1` (`nfc_rules.py:230-232`) par une
fonction `_convector_count(nfc_cat, surface_m2) -> int` appliquée au séjour et
aux chambres lorsque `heating_enabled` :

```
si surface_m2 connue (non None et > 0) :
    return max(1, ceil(surface_m2 / 20))
sinon (repli forfait par type) :
    LIVINGROOM -> 2
    BEDROOM    -> 1
```

Seuil surfacique : **20 m²/convecteur** (≈ 100 W/m², convecteur ~2000 W).

Exemples :
- Chambre 11 m² → `ceil(11/20)=1`
- Séjour 35 m² → `ceil(35/20)=2`
- Séjour 45 m² → `ceil(45/20)=3`
- Séjour, surface inconnue → 2 (repli)
- Chambre, surface inconnue → 1 (repli)

La règle surfacique s'activera automatiquement le jour où les surfaces seront
calculées de façon fiable, sans nouvelle modification.

### Impact tableau

Aucun. Le packing gère déjà jusqu'à 2 convecteurs par circuit 20A
(`CONVECTOR_MAX_PER_CIRCUIT`, `nfc_tableau.py:91`) ; un nombre plus élevé crée
simplement des circuits supplémentaires via `_build_heating_circuits`.

## Hors scope (YAGNI)

- Sèche-serviettes, sèche-linge, cumulus : comportement inchangé.
- Dimensionnement par puissance réelle (W) ou par isolation : non, le seuil
  20 m² est un proxy suffisant pour la V1.
- Calcul des surfaces : hors de ce lot ; on se branche sur `surface_m2`
  existant quand il sera renseigné.

## Tests

Lave-linge :
1. Plan avec cellier → 1 seul lave-linge, pas de doublon.
2. Plan sans cellier mais avec SDB → lave-linge rattaché à la SDB ; DDR Type A
   présent dans le tableau.
3. Priorité de repli : SDB choisie avant cuisine quand les deux existent.
4. Plan sans aucune pièce candidate (que des chambres) → circuit `LAUNDRY`
   Type A présent dans le tableau, Devis synthétique sans pastille.
5. Libellé feed = « Lave-linge (20A) » (nouveau et cellier existant).

Convecteurs :
6. Séjour surface connue 45 m² → 3 convecteurs.
7. Séjour surface inconnue → 2 convecteurs (repli).
8. Chambre surface inconnue → 1 convecteur (repli).
9. Chambre 11 m² → 1 convecteur.
10. `heating_enabled=False` → 0 convecteur (inchangé).
