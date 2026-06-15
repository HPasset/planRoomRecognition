# Schéma unifilaire — format Hager (paysage, bus horizontal) — Design

**Date** : 2026-06-15
**Branche** : `feat/placement-chambre`
**Statut** : validé (brainstorming)
**Remplace** : `docs/superpowers/specs/2026-06-15-schema-unifilaire-design.md` (format portrait colonnes-par-ID, abandonné)

## Objectif

Adopter le **format de schéma unifilaire Hager** (que les électriciens associés valident
déjà) en remplacement de la première version portrait. Cible : fidélité maximale de
**format et de conventions** — rendu programmatique très proche visuellement, pas un
clone pixel-perfect du moteur CAO Hager.

Référence : export Hager `20260520_100726_EtiquettesSchema_De bethman.pdf`, folios 3-5
(le schéma unifilaire ; les folios 1-2 sont les étiquettes, déjà couvertes par
`etiquettes_renderer.py`).

On **conserve** l'infra déjà livrée (extraction `icon_assets.py`, bouton de
téléchargement, pictos d'usage) : seul le **corps du renderer**
`schema_unifilaire.py` est réécrit, plus un petit formulaire UI pour le cartouche.

## Décisions de design (issues du brainstorming)

| Sujet | Décision |
|-------|----------|
| Devenir de la version portrait | (a) **Remplacée** par le format Hager paysage. Infra conservée, historique git conservé. |
| Données du cartouche | (c) **Mix** : Régime `TT` par défaut + Puissance dérivée auto (éditable) ; Projet/Client saisis. |
| Source Client | Sélecteur depuis le **référentiel clients existant** (`list_clients(session, artisan_id)`). |
| Source Projet | **Champ libre** saisi par l'utilisateur. |
| Codes de désignation | (a) **Notations génériques** `DB/ID/Q/JB/CR/L1,N` — **pas** les sigles produit Hager `HDA/CDS/MFS`. |
| Pagination / renvois | (b) **Pagination simplifiée** : cadre normalisé + grille A-G/1-14, continuation « suite folio N », **sans** système de cibles CR. |
| Pictos | **Bibliothèque batIA** (`icon_assets`), pas les pictos Hager. |
| Logo cartouche | **Logo batIA**, pas Hager. |

## 1. Architecture

Réécriture intégrale du **corps** de `src/planrec/schema_unifilaire.py` (format paysage
Hager). Module **pur** : reportlab uniquement, aucun import Streamlit/React/DB.

- Nouvelle dataclass **`CartoucheInfo`** :
  ```python
  @dataclass
  class CartoucheInfo:
      projet: str
      client_nom: str
      client_ville: str
      puissance_kva: int
      regime_neutre: str   # "TT" | "TN" | "IT"
      date_iso: str        # passé par l'appelant (pas de Date.now côté renderer pur)
  ```
- API publique :
  ```python
  def render_schema_unifilaire_pdf(tableau: Tableau, cartouche: CartoucheInfo) -> bytes
  ```
- Le renderer ne touche jamais la DB : la couche Streamlit récupère le client +
  les champs du formulaire et construit `CartoucheInfo`.
- Constantes AGCP/courbe conservées (DEFAULT_CURVE="C", 500 mA sélectif).
- L'infra `icon_assets.load_icon_as_drawing` / `resolve_svg_id_for_circuit` est
  réutilisée pour la bande pictos.

## 2. Page & cadre normalisé

- **A4 paysage** (`landscape(A4)`).
- Cadre Hager : bordure extérieure, **repères de grille colonnes 1-14** (haut et bas)
  + **lignes A-G** (gauche et droite), cartouche en bandeau bas.
- Coordonnées internes en mm (origine bas-gauche reportlab), via un helper de
  conversion comme dans la version précédente.

## 3. Topologie bus horizontal (cœur du rendu)

Lecture gauche → droite, haut → bas :

- **Colonne 1 (gauche)** : libellé vertical **« Application / Localisation des départs »**.
- **Alim. BT** (symbole flèche) → **DB1** : disjoncteur de branchement (symbole
  EN 60617 boîtier + contact), annoté `{calibre} A · 500 mA · S` (calibre dérivé,
  cf. §4).
- **Jeu de barres JB1** horizontal (ligne ~A) ; les **ID** y pendent :
  `ID1` `{amps} A · 30 mA · A`, `ID2` `… AC`, etc. Chaque ID alimente un **bus
  secondaire `JB2`…** qui descend vers ses départs.
- **Disjoncteurs divisionnaires `Q1…Qn`** : traits verticaux dans les colonnes de la
  grille, chacun = symbole disjoncteur + repère `Q{n}` + `C {breaker_amps}A` + `L1,N`.
  Numérotation `Q` **globale et continue** sur tout le tableau (across folios).
- **Barre de terre `PE1`** : trait mixte **vert** (ligne ~E) traversant toute la
  largeur ; liaison terre (symbole) sous chaque départ.
- **Bande « Pictogramme »** (ligne E/F) : picto d'usage **batIA** aligné sous chaque Q
  (`resolve_svg_id_for_circuit`).
- **Localisation** (lignes F/G) : désignation du circuit en **texte vertical** (le
  `circuit.label` : Éclairage, Prises, Plaque cuisson…). **Pas** de liste de pièces.

## 4. Calibres dérivés

- **Puissance prévisionnelle** : défaut selon typologie — `T1`/`T2` → 6, `T3` → 9,
  `T4`/`T5` → 12 kVA. **Éditable** dans l'UI (champ prérempli).
- **DB (AGCP)** : calibre dérivé de la puissance — `6 → 30 A`, `9 → 45 A`,
  `12 → 60 A` (table de mapping ; fallback au plus proche). 500 mA, sélectif (S).
- **ID** : `rcd.amps` / `rcd.sensitivity_ma` / `rcd.rcd_type`.
- **Q** : `circuit.breaker_amps` + courbe **C** (`DEFAULT_CURVE`).

## 5. Pagination

- Grille 14 colonnes → ~11-12 colonnes de départ utiles par folio (constante
  `DEPARTS_PER_FOLIO`).
- Au-delà : nouveau folio, **cadre + cartouche** (`Folio X/N`) redessinés sur chacun ;
  l'arrivée (Alim BT/DB) n'apparaît qu'au folio 1, le bus est poursuivi avec une
  mention sobre **« suite folio N »** en bord de cadre (pas de cibles `ligne,colonne`).
- Cas résidentiel : 1 à 2 folios.
- Tableau vide → 1 folio minimal valide (cadre + cartouche).

## 6. Cartouche (bandeau bas, style Hager)

Grille de cases :

- **Projet** (saisi)
- **Client** : `nom_ou_raison` + `adresse_ville` (depuis le référentiel)
- **Date** (du jour, passée via `CartoucheInfo.date_iso`)
- **Folio X/N**
- **Puissance prévisionnelle** : `{kva} kVA`
- **Régime de neutre** : `TT` (défaut) / `TN` / `IT`
- `Tableau électrique — {typology}`
- **Logo batIA** (réutilise `_draw_batia_logo_cartouche`)

## 7. Intégration Streamlit

Dans `app/streamlit_app.py`, section « ⚡ Tableau électrique », **au-dessus** des boutons
de téléchargement : petit formulaire (dans un `st.expander` ou colonnes) :

- **Projet** : `st.text_input` (défaut vide).
- **Client** : `st.selectbox` peuplé via `list_clients(session, artisan.id)` ; option
  vide possible. Récupère `nom_ou_raison` + `adresse_ville` du client choisi.
- **Puissance (kVA)** : `st.number_input` prérempli avec la valeur dérivée de la
  typologie.
- **Régime de neutre** : `st.selectbox(["TT", "TN", "IT"])`, défaut `TT`.

On construit `CartoucheInfo` (avec `date_iso = date.today().isoformat()`), passé à
`render_schema_unifilaire_pdf`. Le bouton de téléchargement existant
(`dl_schema_unifilaire_pdf`) est conservé, avec son `try/except → st.error`. Si aucun
client n'est sélectionné, le schéma se génère quand même (champ Client vide /
« À compléter »).

Accès session/artisan : réutiliser le pattern des pages facturation
(`SessionLocal` + `artisan`) — à confirmer à l'implémentation ; si l'accès DB est lourd
côté page Home, fallback : champ Client en `text_input` libre (décision d'implémentation
documentée dans le plan, mais le sélecteur référentiel reste la cible).

## 8. Tests (`tests/test_schema_unifilaire.py` — réécrit)

Module pur → tests directs :

- `%PDF` + bytes non vides ;
- nombre de folios cohérent avec le nombre de départs (1 folio nominal ; multi-folios
  forcé avec beaucoup de circuits) ;
- présence des repères de grille (`A`…`G`, `1`…`14`) dans le texte extrait ;
- textes cartouche présents : projet, client, `kVA`, régime, `Folio` ;
- repères `Q1`, `Q2`… globaux et continus ;
- ID annotés type/30 mA ; DB annoté 500 mA + calibre dérivé attendu pour une puissance
  donnée ;
- pictos : tous les `CircuitType` résolvent et rendent sans crash ;
- ligne de terre `PE` présente ;
- tableau vide → 1 folio valide ;
- `CartoucheInfo` dataclass : champs requis.
- Régression Streamlit : le formulaire ne casse pas `tests/test_devis_apptest.py`.

## Hors périmètre (YAGNI)

- Système de renvois CR appariés avec cibles `folio-ligne,colonne` (remplacé par
  « suite folio N »).
- Sigles produit Hager `HDA/CDS/MFS` (notations génériques retenues).
- Pictos volet roulant / VMC / pompe à chaleur / GTL / chauffe-eau : non générés par le
  moteur NFC actuel, donc absents du schéma (on ne rend que nos `CircuitType`).
- Pas de modification du modèle `nfc_tableau.py` (`Tableau` / `RCD` / `Circuit`).
- Pas de second format conservé (le portrait est remplacé).
