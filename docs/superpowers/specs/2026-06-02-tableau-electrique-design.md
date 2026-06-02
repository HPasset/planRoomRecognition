# Tableau électrique batIA — Design V1

**Date** : 2026-06-02
**Auteur** : H. Passet (batIA) + brainstorming assisté
**Source brainstorming** : sessions 2026-06-01 / 2026-06-02 (Sections 1-6 validées + Q1-Q8 + Q archi)

---

## Goal

Générer automatiquement le schéma du tableau électrique d'un logement résidentiel à partir du devis NFC produit par batIA, dans un style proche du rendu Hager Ready (vue modulaire DIN + liste circuits + export PDF A4 prêt-pour-chantier). L'objectif produit : faire gagner aux artisans électriciens le temps de calcul/répartition lors de la démo et de la phase devis.

## Périmètre V1 (validé)

**Inclus** :
- Vue modulaire du tableau : rangées de modules colorés par fonction, ID + disjoncteurs alignés
- Liste descriptive des circuits (type, calibre, section câble, pièces alimentées)
- Export PDF A4 reportlab pour chantier
- Auto-détection typologie depuis les pièces du devis (T1-T5)
- Auto-génération chauffage électrique (toggle global sidebar)
- Calcul des sections de câble par calibre disjoncteur
- Répartition automatique sur les ID (greedy, NFC-compliant)

**Hors V1** (mentions / dégagement de responsabilité) :
- Schéma unifilaire normalisé NFC
- Estimation longueurs de câble + chute de tension
- Coffret VDI (prises RJ45) — mentionné seulement
- Borne IRVE, parafoudre, contacteur HC/HP heures creuses
- Plancher chauffant
- Édition utilisateur (read-only V1)
- Type F (hyper-immunisé)
- Triphasé (V1 = monophasé 230V uniquement)

---

## Architecture

### Vue d'ensemble

Deux nouveaux modules Python, frontière nette entre **logique métier pure** et **rendu** :

```
src/planrec/
├── nfc_rules.py          ← MODIF : éclater SPECIAL_FEED en 6 sous-types + 2 chauffage
├── nfc_equipments.py     ← MODIF : ajouter nouveaux types dans EQUIP_TYPES
├── nfc_pricing.py        ← MODIF : prix unitaires des nouveaux types
├── nfc_tableau.py        ← NOUVEAU : logique métier 100% pure (pytest pur)
│                            typologie, calcul disjoncteurs, répartition ID, calibrage
└── tableau_renderer.py   ← NOUVEAU : rendu SVG + PDF reportlab
                             (consomme un Tableau produit par nfc_tableau)
```

### Flow de données

```
[Devis NFC global]
    ↓ (lignes par pièce × type d'équipement, source de vérité)
[nfc_tableau.generate_tableau(devis, options)]
    ↓ (algo greedy en 7 phases)
[Tableau dataclass]
    ↓
    ├─→ [tableau_renderer.render_svg(tableau)]      → SVG inline pour st.markdown
    ├─→ [tableau_renderer.render_html_table(tableau)] → tableau HTML descriptif
    └─→ [tableau_renderer.export_pdf(tableau)]      → bytes PDF reportlab pour st.download_button
```

### Intégration UI

Une nouvelle section "⚡ Tableau électrique" en bas de la page Streamlit actuelle, gated par le click "Générer devis" (même gate que la section devis). Pas de nouvel onglet, pas de page multipage — l'user scroll : plan + équipements → devis → tableau → bouton PDF.

Sidebar : 1 toggle "Chauffage électrique" (default ON) + 1 expander "Forcer typologie" (override optionnel).

---

## Modèle de données — refactor `EquipmentType`

L'enum actuel a 5 valeurs dont une seule fourre-tout `SPECIAL_FEED` pour TOUS les circuits spécialisés. Pour générer un tableau correct, il faut typer chaque appareil.

### Avant (état actuel)

```python
class EquipmentType(str, Enum):
    SOCKET = "prise_courant"
    RJ45 = "prise_rj45"
    LIGHT_POINT = "point_lumineux"
    SWITCH = "interrupteur"
    SPECIAL_FEED = "alimentation_specialisee"  # fourre-tout
```

### Après

```python
class EquipmentType(str, Enum):
    # Inchangés
    SOCKET = "prise_courant"
    RJ45 = "prise_rj45"
    LIGHT_POINT = "point_lumineux"
    SWITCH = "interrupteur"
    # NEW : éclatement de SPECIAL_FEED en sous-types typés
    OVEN = "four"
    COOKTOP = "plaque_cuisson"
    DISHWASHER = "lave_vaisselle"
    WASHING_MACHINE = "lave_linge"
    DRYER = "seche_linge"
    BOILER = "chaudiere_cumulus"
    # NEW : chauffage
    CONVECTOR = "convecteur"
    TOWEL_WARMER = "seche_serviettes"
```

### Génération auto des équipements depuis le devis

`compute_devis_global` doit créer les sous-types selon la pièce :
- **Cuisine** : OVEN ×1, COOKTOP ×1, DISHWASHER ×1 (au lieu de SPECIAL_FEED ×3)
- **Buanderie** : WASHING_MACHINE ×1, DRYER ×1 (au lieu de SPECIAL_FEED ×2)
- **SdB/Chaufferie** : BOILER ×1 (au lieu de SPECIAL_FEED ×1)
- **Pièces principales** (séjour, chambres) : CONVECTOR ×1 si toggle chauffage ON
- **SdB** : TOWEL_WARMER ×1 si toggle chauffage ON

### Impact sur l'existant

| Fichier | Changement |
|---|---|
| `src/planrec/nfc_rules.py` | Remplacer `SPECIAL_FEED` par sous-types dans `compute_devis_global` |
| `src/planrec/nfc_equipments.py` | Étendre `EQUIP_TYPES` dict (couleur + svg_id par sous-type) + `NFC_TO_EQUIP_TYPE` mapping |
| `src/planrec/nfc_pricing.py` | Prix unitaire par sous-type (estimation marché 2026) |
| `app/streamlit_app.py` | Mapping label devis pour chaque type (`"Four"`, `"Plaque de cuisson"`, etc.) + `_EQUIP_TYPE_TO_DEVIS_LABEL` étendu |
| `tests/test_nfc_equipments.py` | Adapter `test_generate_equipments_kitchen_qty_explodes` (compte Four+Plaque+LV au lieu de 3× SPECIAL_FEED) |
| `tests/test_devis_apptest.py` | Adapter compteurs (lignes "Prise spé" en cuisine deviennent "Four", "Plaque", "LV") |
| `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` | Ajouter 8 nouveaux SVG icônes (style NF EN 60617 stylisé) : four, plaque, LL, SL, LV, chaudière, convecteur, sèche-serviettes |

### Palette couleurs équipements (cohérent avec rendu tableau)

| Catégorie | Couleur CSS |
|---|---|
| Éclairage | `#FFD54F` (jaune) |
| Prises courant | `#42A5F5` (bleu) |
| RJ45 | `#26A69A` (vert) |
| Cuisine spé (Four, Plaque, LV) | `#AB47BC` (violet) |
| Buanderie (LL, SL) | `#FF7043` (orange) |
| Chaudière/cumulus | `#C62828` (rouge sombre) |
| Chauffage (Convecteur, Sèche-serv.) | `#EF5350` (rouge clair) |

---

## Algorithme de répartition

### Dataclasses

```python
class CircuitType(str, Enum):
    LIGHTING        = "lighting"          # 10A
    SOCKET          = "socket"            # 20A
    KITCHEN_SPECIAL = "kitchen_special"   # Four / Plaque / LV (20A ou 32A)
    LAUNDRY         = "laundry"           # LL / SL (20A)
    BOILER          = "boiler"            # Chaudière / cumulus (20A)
    HEATING         = "heating"           # Convecteur (20A)
    TOWEL_WARMER    = "towel_warmer"      # Sèche-serviettes SdB (20A)


@dataclass
class Circuit:
    id: str                       # "circ_<8 hex>"
    type: CircuitType             # cf. enum ci-dessus
    label: str                    # "Prises Cuisine + Séjour"
    breaker_amps: int             # 10, 20, 32
    cable_section_mm2: float      # 1.5, 2.5, 6.0
    rooms_served: list[str]       # ["Cuisine", "Séjour"]
    n_devices: int                # nb équipements alimentés
    requires_type_a: bool         # True pour COOKTOP + WASHING_MACHINE

@dataclass
class RCD:                        # Interrupteur Différentiel
    id: str
    rcd_type: str                 # "A" (plaque + LL obligatoire) ou "AC"
    amps: int                     # 25, 40, 63, 80, 100, 125 (normalisé)
    sensitivity_ma: int           # 30 mA (résidentiel standard)
    circuits: list[Circuit]       # max 8

@dataclass
class Tableau:
    typology: str                 # "T3"
    typology_source: str          # "auto" | "user_override"
    surface_m2: float | None      # si dispo dans devis pour règle NFC stricte
    heating_enabled: bool
    rcds: list[RCD]
    total_modules: int            # somme circuits + ID + 20% headroom (futur)
    n_rails: int                  # ceil(total_modules / 13 par rail Hager standard)
    notes: list[str]              # ex "5 prises RJ45 → coffret VDI séparé"
    warnings: list[str]           # cas limites (ex "T1 avec >8 disjoncteurs forcés sur 2 ID")
```

### Algo greedy — 7 phases

**Entrée** : `DevisGlobal` + `options = {heating_enabled: bool, typology_override: str | None}`

#### Phase 1 — Mention RJ45 (hors tableau)

Les prises RJ45 ne vont **pas** dans le tableau de puissance (coffret VDI séparé). Action : compter les RJ45 du devis, ajouter à `tableau.notes` : `"{N} prises RJ45 → coffret VDI séparé (hors V1)"`. Aucun circuit créé.

#### Phase 2 — Circuits éclairage (bin-packing 5 lights/circuit)

- Pour chaque pièce, compter `LIGHT_POINT`. Trier pièces par n_lights décroissant.
- Greedy : ouvrir 1 circuit (capacité 5). Tant qu'on peut ajouter une pièce sans dépasser 5 : add. Sinon nouveau circuit.
- Chaque circuit lighting = disjoncteur 10A, section 1.5 mm².

#### Phase 3 — Circuits prises courant (bin-packing 12 sockets/circuit, "même pièce préférée")

- Trier pièces par n_sockets décroissant.
- Greedy : pièces ≤12 prises → 1 circuit chacune. Pièces avec <6 prises packées ensemble si capacité restante.
- Chaque circuit socket = disjoncteur 20A, section 2.5 mm².

#### Phase 4 — Circuits chauffage (si toggle ON)

- Auto-générer convecteurs : 1× 2000W par pièce principale (séjour + chambres) = `CONVECTOR`.
- Auto-générer sèche-serviettes : 1× 1000W par SdB = `TOWEL_WARMER`.
- Packer 2 convecteurs max par circuit (20A, 2.5 mm²).
- Sèche-serviettes : 1 circuit spécialisé dédié 20A.

#### Phase 5 — Circuits spécialisés (1 disjoncteur par appareil)

- 1 circuit par instance d'appareil :
  - `OVEN` → 20A, 2.5 mm²
  - `COOKTOP` → **32A, 6 mm²**, `requires_type_a=True`
  - `DISHWASHER` → 20A, 2.5 mm²
  - `WASHING_MACHINE` → 20A, 2.5 mm², `requires_type_a=True`
  - `DRYER` → 20A, 2.5 mm²
  - `BOILER` → 20A, 2.5 mm²

#### Phase 6 — Calcul nombre min d'ID

```python
n_id_required = max(
    n_id_typo,        # règle associé : T1=1, T2=2, T3=3, T4=4, T5=4
    n_id_surface,     # règle NFC : <=35m²=1, 36-100=2, >100=3
    ceil(total_breakers / 8),  # contrainte hard max 8 disj/ID
)
```

`n_id_surface` calculé seulement si `surface_m2` disponible dans le devis. Sinon ignoré (la règle typo s'applique).

#### Phase 7 — Répartition sur les ID

1. **Créer ID 1 Type A** → y placer obligatoirement les circuits `requires_type_a` (= Plaque + Lave-linge).
2. Créer `n_id_required - 1` autres ID Type AC.
3. Trier les autres disjoncteurs par calibre décroissant (32A en premier, puis 20A, puis 10A).
4. Bin-packing greedy : pour chaque disjoncteur, le placer dans l'ID le moins chargé (en nombre de disj, capacité max 8) en privilégiant l'équilibre.
5. **Calcul du calibre de chaque ID** :
   ```
   non_heating_circuits = [c for c in rcd.circuits
                            if c.type not in (HEATING, TOWEL_WARMER)]
   heating_circuits     = [c for c in rcd.circuits
                            if c.type in (HEATING, TOWEL_WARMER)]
   amps_id = ceil_to_normalized(
       sum(c.breaker_amps for c in non_heating_circuits) / 2
       + sum(c.breaker_amps for c in heating_circuits)  # somme si plusieurs
   )
   ```
   où `ceil_to_normalized(x)` arrondit à `[25, 40, 63, 80, 100, 125]` supérieur.
   En résidentiel typique : 40A ou 63A.

   **Note** : si plusieurs circuits chauffage cohabitent sur le même ID (cas
   rare en pratique car on essaie de les répartir), leurs calibres sont
   sommés au lieu de divisés par 2 — interprétation conservatrice de la règle
   cabinet associé "ajouter le calibre du chauffage s'il y en a".

### Edge cases gérés

- **T1 avec 1 seul ID** → ID Type A unique, contient Plaque + LL + tout le reste (max 8 circuits, sinon ajout ID supplémentaire forcé).
- **>8 disjoncteurs requis** → ajout ID supplémentaire au-delà du min réglementaire (contrainte 3 dans Phase 6).
- **Pas de Plaque ni LL** (rare, ex cuisine gaz pure sans LL/SL) → pas d'ID Type A obligatoire, tous AC.
- **Convecteurs en nombre impair** → dernier circuit chauffage avec 1 seul convecteur.

---

## Règles métier — table complète

### Circuits par type

| Type | Calibre disj. | Section câble | Max appareils | Source |
|---|---|---|---|---|
| Éclairage (points lumineux) | 10 A | 1.5 mm² | **5** | Règle cabinet associé |
| Éclairage (spots) | 10 A | 1.5 mm² | 12 | Règle cabinet associé (non distinguable V1) |
| Prises de courant | 20 A | 2.5 mm² | **12** | Règle cabinet associé |
| Chauffage (convecteurs) | 20 A | 2.5 mm² | 2× 2000 W max | Règle cabinet associé |
| Sèche-serviettes (SdB) | 20 A | 2.5 mm² | 1 (circuit spé) | NFC §10 |
| Four | 20 A | 2.5 mm² | 1 | NFC §10 |
| **Plaque cuisson** | **32 A** | **6 mm²** | 1, **ID Type A** | NFC §10 |
| Lave-linge | 20 A | 2.5 mm² | 1, **ID Type A** | NFC §10 |
| Sèche-linge | 20 A | 2.5 mm² | 1 | NFC §10 |
| Lave-vaisselle | 20 A | 2.5 mm² | 1 | NFC §10 |
| Chaudière/cumulus | 20 A | 2.5 mm² | 1 | NFC §10 |

**Divergence règle associé vs NFC stricte** (à confirmer en review avant impl) :
- NFC stricte = 8 points lumineux max et 8 prises max par circuit.
- Cabinet associé pratique 5/12 (marge sécu lumière, prises 20A vs 16A NFC).
- **Choix V1 : règles cabinet associé** (pratique terrain prioritaire).

### Règles ID

- **Max 8 disjoncteurs par ID** (NFC art 771.422.0.1)
- **Type A obligatoire pour** : Plaque cuisson + Lave-linge
- **Type AC** pour tous les autres circuits par défaut
- **Sensibilité 30 mA** (résidentiel standard)
- **Calibre ID** = `(Σ amps_disj_hors_chauffage) / 2 + amps_chauffage`, arrondi au calibre normalisé supérieur ∈ {25, 40, 63, 80, 100, 125 A}

### Min ID par logement

V1 prend le **max** de 3 contraintes :
1. Règle associé (par typologie) : T1=1, T2=2, T3=3, T4=4, T5=4
2. Règle NFC stricte (par surface, si dispo) : ≤35 m²=1, 36-100=2, >100=3
3. `ceil(total_disjoncteurs / 8)` (contrainte hard max 8 disj/ID)

---

## Rendu visuel — SVG + PDF

### Layout du schéma modulaire

Représentation type Hager Ready : rangées DIN avec ID à gauche + disjoncteurs alignés à droite.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Tableau électrique — Logement T3 — 2026-XX-XX                              │
├────────────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────────┤
│            │ 10A │ 10A │ 20A │ 20A │ 20A │ 32A │ 20A │ 20A │     │         │
│  ID 1      │     │     │     │     │     │  *  │  *  │     │     │         │
│  40 A      │ Lum │ Lum │ Pr. │ Pr. │ Pr. │Plaq │ LL  │ Four│     │         │
│  Type A    │ Sjr │ Cbr │ Sjr │ Cuis│ Cbr │     │     │     │     │         │
│  30 mA     │ 1.5 │ 1.5 │ 2.5 │ 2.5 │ 2.5 │ 6.0 │ 2.5 │ 2.5 │     │         │
├────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────────┤
│  ID 2      │ 10A │ 20A │ 20A │ 20A │ 20A │ 20A │ 20A │     │     │         │
│  63 A      │ Lum │ Pr. │ Pr. │ Pr. │ LV  │ SL  │Chaud│     │     │         │
│  Type AC   │ Cuis│ SdB │ WC  │ Bua │     │     │     │     │     │         │
│  30 mA     │ 1.5 │ 2.5 │ 2.5 │ 2.5 │ 2.5 │ 2.5 │ 2.5 │     │     │         │
├────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────────┤
│  ID 3      │ 20A │ 20A │ 20A │     │     │     │     │     │     │         │
│  40 A      │ Conv│ Conv│Sech │     │     │     │     │     │     │         │
│  Type AC   │ 1+2 │ 3+4 │ Serv│     │     │     │     │     │     │         │
│  30 mA     │ 2.5 │ 2.5 │ 2.5 │     │     │     │     │     │     │         │
└────────────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────────┘
                                                              (* = Type A obligatoire)
```

### Dimensions SVG

| Élément | Dimensions |
|---|---|
| Module disjoncteur (standard) | 60 × 100 px |
| Bloc ID (à gauche, largeur fixe 4 modules) | 240 × 100 px |
| 1 rangée complète | `240 + 18×60 = 1320 px` de large |
| Tableau total | `N rangées × 100 px + 50 px header` de haut |
| Fond | `#FAFAFA` |
| Bordure module | `#37474F` 1 px |
| Header module (calibre) | noir bold 14 px |
| Label module (fonction) | noir 11 px |
| Section câble (en bas) | gris foncé italic 9 px |

### Code couleurs par fonction de circuit

| Type Circuit | Couleur SVG |
|---|---|
| `CircuitType.LIGHTING` | `#FFD54F` |
| `CircuitType.SOCKET` | `#42A5F5` |
| `CircuitType.KITCHEN_SPECIAL` (Four/Plaque/LV) | `#AB47BC` |
| `CircuitType.LAUNDRY` (LL/SL) | `#FF7043` |
| `CircuitType.BOILER` | `#C62828` |
| `CircuitType.HEATING` (Convecteur) | `#EF5350` |
| `CircuitType.TOWEL_WARMER` | `#EF9A9A` |

### Liste circuits HTML (sous le schéma)

Tableau structuré pour aider l'artisan à câbler. Colonnes :

| ID | Type | Calibre | Section | Pièces alimentées |
|---|---|---|---|---|
| ID 1 Type A | Éclairage | 10 A | 1.5 mm² | Séjour |
| ID 1 Type A | Éclairage | 10 A | 1.5 mm² | Chambre 1, Chambre 2 |
| ID 1 Type A | Prises | 20 A | 2.5 mm² | Séjour |
| ID 1 Type A | **Plaque cuisson** | **32 A** | **6 mm²** | Cuisine |
| ... | ... | ... | ... | ... |

### Export PDF (reportlab)

- Format **A4 portrait**
- En-tête : `batIA · Tableau électrique · T<X> · <date> · <ref logement>`
- Section "Schéma modulaire" : reportlab `Canvas` direct (Rect + drawString) — pas de conversion SVG, on a déjà les coords en Python
- Section "Détail des circuits" : `reportlab.platypus.Table` avec style alternance lignes
- Pied de page : `Calculé selon NFC 15-100 §10 + règles cabinet. Sections câbles indicatives. L'artisan valide la conformité finale.`

### Module Python

```python
# src/planrec/tableau_renderer.py

CIRCUIT_COLORS: dict[CircuitType, str] = {
    CircuitType.LIGHTING:        "#FFD54F",
    CircuitType.SOCKET:          "#42A5F5",
    CircuitType.KITCHEN_SPECIAL: "#AB47BC",
    CircuitType.LAUNDRY:         "#FF7043",
    CircuitType.BOILER:          "#C62828",
    CircuitType.HEATING:         "#EF5350",
    CircuitType.TOWEL_WARMER:    "#EF9A9A",
}

def render_svg(tableau: Tableau) -> str:
    """Génère le SVG complet du tableau comme string XML.
    Sortie embarquable directement dans st.markdown(unsafe_allow_html=True)."""

def render_html_table(tableau: Tableau) -> str:
    """Génère le tableau HTML descriptif des circuits."""

def export_pdf(tableau: Tableau) -> bytes:
    """Génère le PDF A4 (schéma + liste). Bytes pour st.download_button."""
```

---

## UI Streamlit

### Sidebar — nouveau bloc

```python
with st.sidebar:
    st.subheader("⚡ Tableau électrique")
    heating_enabled = st.toggle(
        "Chauffage électrique",
        value=True,
        help="Si actif, batIA ajoute 1 convecteur 2000W par pièce "
             "principale et 1 sèche-serviettes par SdB."
    )
    with st.expander("Forcer typologie"):
        typology_override = st.selectbox(
            "Typologie", [None, "T1", "T2", "T3", "T4", "T5"],
            help="Par défaut auto-détectée depuis les pièces."
        )
```

### Section principale — en bas après le devis

```python
# Apparition gated par le click "Générer devis" (gate existant)
if st.session_state.get(_devis_triggered_key):
    st.markdown("---")
    st.subheader("⚡ Tableau électrique")

    tableau = nfc_tableau.generate_tableau(
        devis_global=devis_global,
        heating_enabled=heating_enabled,
        typology_override=typology_override,
    )

    # Bandeau de notes / warnings
    for note in tableau.notes:
        st.info(note)
    for warning in tableau.warnings:
        st.warning(warning)

    # Schéma modulaire SVG
    svg_xml = tableau_renderer.render_svg(tableau)
    st.markdown(svg_xml, unsafe_allow_html=True)

    # Liste circuits HTML
    st.markdown("**Détail des circuits**")
    html_circuits = tableau_renderer.render_html_table(tableau)
    st.markdown(html_circuits, unsafe_allow_html=True)

    # PDF download
    pdf_bytes = tableau_renderer.export_pdf(tableau)
    st.download_button(
        "📄 Télécharger le tableau (PDF A4)",
        data=pdf_bytes,
        file_name=f"tableau_electrique_{tableau.typology}_{img_hash[:8]}.pdf",
        mime="application/pdf",
    )
```

---

## Tests

3 niveaux comme déjà fait sur la feature équipements V1 :

### Unit pytest sur `tests/test_nfc_tableau.py` (~15-20 tests)

- `test_detect_typology_T2_from_rooms` (1 séjour + 1 chambre → T2)
- `test_detect_typology_T3_from_rooms`
- `test_detect_typology_T5_capped` (4+ chambres → T5)
- `test_min_rcds_uses_max_of_typology_surface_and_breakers_8`
- `test_lighting_bin_packing_5_per_circuit`
- `test_socket_bin_packing_12_per_circuit_same_room_preferred`
- `test_heating_2_convectors_per_circuit_20A`
- `test_heating_disabled_no_heating_circuit`
- `test_specialized_each_appliance_1_breaker`
- `test_plaque_32A_cable_6mm2`
- `test_type_A_rcd_contains_plaque_and_washing_machine`
- `test_rcd_amps_formula_excludes_heating_divides_by_2`
- `test_rcd_amps_rounded_up_to_normalized` (40/63/80/125)
- `test_edge_case_T1_one_rcd_type_A_all_circuits_on_it`
- `test_edge_case_many_breakers_force_additional_rcd`
- `test_rj45_not_in_circuits_but_in_notes`
- `test_no_kitchen_no_cooktop_no_type_a_rcd_required`

### Unit pytest sur `tests/test_tableau_renderer.py` (~6 tests)

- `test_render_svg_well_formed_xml`
- `test_render_svg_contains_all_circuits_as_rect`
- `test_render_html_table_one_row_per_circuit`
- `test_export_pdf_returns_valid_pdf_bytes` (parse avec `pypdf`)
- `test_color_for_each_circuit_type_correctly_mapped`
- `test_svg_dimensions_scale_with_n_rcds`

### AppTest sur `tests/test_devis_apptest.py` (~5 nouveaux tests T1-T5)

- `test_T1_tableau_appears_after_devis_trigger`
- `test_T2_toggle_heating_off_no_heating_circuits`
- `test_T3_logement_has_at_least_3_rcds`
- `test_T4_pdf_download_button_present_and_returns_bytes`
- `test_T5_typology_override_changes_n_rcds`

---

## Phases d'implémentation

À détailler par writing-plans dans une étape suivante.

| Phase | Périmètre | Effort | Sortie |
|---|---|---|---|
| 1 | Refactor `nfc_rules.py` — éclater SPECIAL_FEED en 6 sous-types + adapter tests existants | 0.5j | 62 tests existants passent (compteurs adaptés) |
| 2 | Module `nfc_tableau.py` : typologie, circuits, RCD, répartition (TDD strict) | 2j | 15-20 tests pytest verts |
| 3 | `tableau_renderer.py` : SVG inline + couleurs + liste HTML | 1j | Rendu visible dans Streamlit |
| 4 | `tableau_renderer.py` : export PDF reportlab + tests | 0.5-1j | Download fonctionne |
| 5 | Intégration `streamlit_app.py` + 5 tests AppTest | 0.5j | E2E démo prête |
| 6 | Polish + journal + spec coverage check | 0.5j | Spec valide, démo OK |

**Total estimé : ~5j ouvrés**.

---

## Risques identifiés et mitigations

| Risque | Mitigation |
|---|---|
| Refacto SPECIAL_FEED casse les tests AppTest existants | TDD strict en Phase 1, adapter les compteurs en série, ne pas avancer tant que les 62 tests existants ne passent pas |
| SVG inline mal supporté Streamlit (sanitization HTML) | Fallback prévu : générer PNG via cairosvg + `st.image` |
| reportlab PDF mal rendu sur certains visualiseurs | Test croisé Preview macOS + Chrome PDF viewer + AdobeReader avant validation Phase 4 |
| Algo répartition ne converge pas sur edge cases T5 chargés | Fixtures explicites T1/T2/T3/T4/T5 dès Phase 2 + warnings dans `Tableau.warnings` si placement non-optimal |
| Divergence règles associé vs NFC stricte non confirmée | Review humaine de la spec avec l'associé avant Phase 2 |

---

## Dépendances ajoutées

- `reportlab` (PyPI) : génération PDF — déjà mature, MIT licence, ~3 MB
- (optionnel fallback) `cairosvg` : conversion SVG → PNG si Streamlit sanitize

---

## Hors V1 (rappel pour roadmap V2+)

- Schéma unifilaire normalisé NFC §10 (avec représentation câbles + sections explicites)
- Estimation longueur câbles + chute de tension (nécessite position tableau sur le plan)
- Coffret VDI (RJ45) : représentation séparée
- Édition utilisateur (drag-drop modules, renommage labels)
- Borne IRVE, parafoudre, contacteur HC/HP, plancher chauffant, Type F
- Triphasé 400V

---

## Annexes — décisions actées dans le brainstorming

- **Q1** : V1 cible = clone visuel Hager Ready (modulaire + liste + PDF)
- **Q2** : Éclater SPECIAL_FEED en 6 sous-types + 2 chauffage (modèle typé)
- **Q3** : Vue modulaire + liste + PDF (PAS schéma unifilaire V1)
- **Q4** : Section en bas page Streamlit actuelle (pas d'onglet)
- **Q5** : Typologie auto-détectée depuis pièces du devis
- **Q6** : Chauffage électrique auto + toggle sidebar (default ON)
- **Q7** : Sections câbles affichées, longueurs hors V1
- **Q8** : Read-only V1 (pas d'édition utilisateur)
- **Archi** : Python pur + SVG inline + reportlab PDF (zero React)
