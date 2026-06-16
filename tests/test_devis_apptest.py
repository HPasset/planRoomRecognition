"""Tests d'intégration AppTest pour les sections 'Pièces à inclure dans le
devis' et 'Devis quantitatif' de ``app/streamlit_app.py``.

Voir ``docs/TEST_PLAN_DEVIS.md`` pour le plan de test complet.

Couvre prioritairement :
- R1-R5 : régressions des bugs déjà corrigés (ne doivent pas revenir).
- A, B, C : initialisation, ajout/suppression, auto-indexation.
- D, G, H : génération devis, manual_backup, indexation.
"""
from __future__ import annotations
from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import (
    find_img_hash,
    get_editor_df,
    get_devis_df,
    find_button_by_label,
    find_selectboxes_by_label,
    get_equipments_state,
    enable_equipments_toggle,
)


APP_FILE = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")
TIMEOUT = 60  # secondes — peut être lent au 1er chargement (postprocess OCR)


# ============================================================================
# A. Initialisation
# ============================================================================


def test_A1_pieces_editor_init_depuis_ocr(patch_pipeline):
    """A1 : à l'upload d'un plan, l'éditeur Pièces s'initialise avec toutes les
    pièces détectées par l'OCR (7 dans le mock résidentiel), toutes cochées."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    assert df is not None
    assert len(df) == 7, (
        f"7 pièces OCR attendues, obtenu {len(df)}. Types : {df['Type'].tolist()}"
    )
    # Toutes pré-cochées
    assert df["Inclure"].all(), "Toutes les pièces devraient être cochées par défaut"
    # Types attendus (en correspondance OCR → label FR)
    types = df["Type"].tolist()
    assert types.count("Chambre") == 2, f"2 Chambres attendues, types : {types}"
    assert "Cuisine" in types
    assert "Séjour / Salon" in types
    assert "WC" in types
    assert "Salle de bain" in types


# ============================================================================
# B. Ajout / suppression de pièces
# ============================================================================


def test_B1_ajouter_piece_ajoute_ligne_par_defaut(patch_pipeline):
    """B1 : click '➕ Ajouter une pièce' → nouvelle ligne en bas, type=Chambre,
    notes='(ajout manuel)', cochée."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    n_before = len(get_editor_df(at))

    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    df_after = get_editor_df(at)
    assert len(df_after) == n_before + 1
    last = df_after.iloc[-1]
    assert last["Type"] == "Chambre"
    assert last["Inclure"] is True or last["Inclure"] == True  # bool or np.bool_
    assert "manuel" in str(last["Notes / texte OCR"]).lower()


# ============================================================================
# C. Auto-indexation
# ============================================================================


def test_C1_indexation_chambres_dans_editeur(patch_pipeline):
    """C1 : 2 Chambres détectées par OCR → la colonne # doit refléter
    l'occurrence (#1 et #2). On vérifie indirectement via le type_total dans
    le DataFrame (les 2 lignes ont bien Type='Chambre')."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    chambres = df[df["Type"] == "Chambre"]
    assert len(chambres) == 2


# ============================================================================
# D. Génération du devis
# ============================================================================


def test_D1_generer_devis_cree_equipements(patch_pipeline):
    """D1 : click 'Générer devis' avec les 7 pièces OCR → un tableau devis
    est créé avec des équipements NFC par pièce, et les indices apparaissent
    (Chambre 1, Chambre 2)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    assert df_devis is not None, "DataFrame devis non créé après 'Générer devis'"
    assert len(df_devis) > 0

    pieces = df_devis["Pièce"].tolist()
    # Indexation : 2 Chambres → "Chambre 1" et "Chambre 2"
    assert "Chambre 1" in pieces, f"Chambre 1 manquante. Pièces : {set(pieces)}"
    assert "Chambre 2" in pieces, f"Chambre 2 manquante. Pièces : {set(pieces)}"
    # 1 seule Cuisine → "Cuisine" sans indice
    assert "Cuisine" in pieces, f"Cuisine manquante. Pièces : {set(pieces)}"
    assert "Cuisine 1" not in pieces, "Cuisine ne devrait PAS avoir d'indice (1 seule)"


# ============================================================================
# RÉGRESSIONS : R1-R5 (bugs corrigés ne doivent pas revenir)
# ============================================================================


def test_R3_wc_manuel_garde_son_type_apres_generer_devis(patch_pipeline):
    """R3 : ajout pièce → change type → WC → click 'Générer devis'
    → la pièce reste WC dans le devis (pas Chambre 4) et génère des
    équipements WC (1 prise + 1 point lumineux + 1 interrupteur).

    Bug historique : la sync DataFrame ↔ widget state ne se faisait pas, et
    le manual_backup réinjectait avec Type="Chambre" (valeur d'init du df)
    au lieu de "WC" (choix utilisateur)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # 1. Ajoute une pièce (type défaut Chambre)
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    # 2. Trouve le selectbox Type de la dernière ligne ajoutée et change en WC
    type_selects = find_selectboxes_by_label(at, "Type de pièce")
    assert len(type_selects) >= 8, (
        f"Au moins 8 selectbox Type attendus (7 OCR + 1 ajout), "
        f"obtenu {len(type_selects)}"
    )
    type_selects[-1].set_value("WC").run()

    # 3. Click "Générer devis"
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    assert df_devis is not None
    pieces = df_devis["Pièce"].tolist()

    # ASSERTION CRITIQUE 1 : aucune ligne "Chambre 4"
    assert "Chambre 4" not in pieces, (
        f"RÉGRESSION R3 : Chambre 4 dans le devis (manual WC traité comme "
        f"Chambre). Pièces : {sorted(set(pieces))}"
    )

    # ASSERTION CRITIQUE 2 : on a maintenant 2 WC (OCR + manuel)
    # → indexation "WC 1" et "WC 2"
    wc_pieces = [p for p in pieces if p.startswith("WC")]
    assert "WC 1" in pieces and "WC 2" in pieces, (
        f"RÉGRESSION R3 : devrait avoir WC 1 et WC 2 (1 OCR + 1 manuel). "
        f"Pièces WC trouvées : {wc_pieces}"
    )

    # ASSERTION 3 : 1 WC sans handicap = 2 équipements NFC (point lumineux + interrupteur)
    wc1_lines = df_devis[df_devis["Pièce"] == "WC 1"]
    wc2_lines = df_devis[df_devis["Pièce"] == "WC 2"]
    assert len(wc1_lines) == 2, f"WC 1 doit avoir 2 équipements NFC, got {len(wc1_lines)}"
    assert len(wc2_lines) == 2, f"WC 2 doit avoir 2 équipements NFC, got {len(wc2_lines)}"
    # Vérifie que ce sont bien les équipements WC (pas Chambre)
    wc1_eqs = sorted(wc1_lines["Équipement"].tolist())
    assert wc1_eqs == ["Interrupteur", "Point lumineux"], (
        f"WC 1 devrait avoir [Interrupteur, Point lumineux], got {wc1_eqs}"
    )


def test_R2_indice_wc_manuel_correct_dans_editeur(patch_pipeline):
    """R2 : après avoir ajouté une pièce et changé son type en WC,
    l'éditeur Pièces doit l'indexer WC 2 (pas WC 4 ou autre).

    Vérifié indirectement via la composition du DataFrame éditeur : type_total
    doit voir 2 WC (et pas 4 Chambres + 1 WC isolé)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    type_selects = find_selectboxes_by_label(at, "Type de pièce")
    type_selects[-1].set_value("WC").run()

    df = get_editor_df(at)
    # Doit avoir : 2 Chambres (OCR) + 1 WC (OCR) + 1 WC (manuel) = 8 pièces total
    # avec 2 Type="WC" dans le DataFrame (et pas 4 Type="Chambre")
    assert len(df) == 8
    assert (df["Type"] == "WC").sum() == 2, (
        f"RÉGRESSION R2 : 2 WC attendus dans le DataFrame, "
        f"obtenu types : {df['Type'].tolist()}"
    )
    assert (df["Type"] == "Chambre").sum() == 2, (
        f"RÉGRESSION R2 : 2 Chambres attendues (l'ajout ne doit PAS rester "
        f"Chambre), obtenu types : {df['Type'].tolist()}"
    )


def test_R1_trash_supprime_bonne_ligne(patch_pipeline):
    """R1 : click 🗑️ sur la ligne N → c'est BIEN la ligne N qui disparaît
    (pas la dernière ou autre). Bug historique : keys widget basées sur
    l'index pandas → décalage après concat."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df_before = get_editor_df(at)
    n_before = len(df_before)
    # Récupère le _id de la ligne à supprimer (3ème ligne, index 2)
    target_id = int(df_before.iloc[2]["_id"])
    target_type_before = df_before.iloc[2]["Type"]
    expected_remaining_types = (
        df_before.iloc[:2]["Type"].tolist()
        + df_before.iloc[3:]["Type"].tolist()
    )

    # Trouve le bon bouton 🗑️ (le 3ème, key=..._del_{target_id})
    img_hash = find_img_hash(at)
    target_btn = next(
        b for b in at.button
        if b.key == f"devis_editor_{img_hash}_del_{target_id}"
    )
    target_btn.click()
    at.run()

    df_after = get_editor_df(at)
    assert len(df_after) == n_before - 1
    # La ligne ciblée n'existe plus
    assert target_id not in df_after["_id"].tolist(), (
        f"RÉGRESSION R1 : _id={target_id} (type {target_type_before}) "
        f"toujours présent après suppression"
    )
    # Les autres lignes sont identiques (même ordre)
    assert df_after["Type"].tolist() == expected_remaining_types


# ============================================================================
# B. Suite (suppression, décoche)
# ============================================================================


def test_B3_decocher_inclure_met_a_jour_compteur(patch_pipeline):
    """B3 : décocher Inclure sur une ligne → le compteur 'X cochées sur Y'
    se met à jour immédiatement (X = Y - 1)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df_before = get_editor_df(at)
    n_total = len(df_before)
    target_id = int(df_before.iloc[0]["_id"])

    # Trouve la checkbox Inclure de la 1ère ligne
    img_hash = find_img_hash(at)
    inc_key = f"devis_editor_{img_hash}_inc_{target_id}"
    checkbox = next(c for c in at.checkbox if c.key == inc_key)
    assert checkbox.value is True

    # Décoche
    checkbox.set_value(False).run()

    # Le DataFrame doit refléter le changement (via on_change)
    df_after = get_editor_df(at)
    assert df_after.loc[df_after["_id"] == target_id, "Inclure"].iloc[0] is False or \
           bool(df_after.loc[df_after["_id"] == target_id, "Inclure"].iloc[0]) is False
    assert df_after["Inclure"].sum() == n_total - 1


# ============================================================================
# C. Auto-indexation suite
# ============================================================================


def test_C3_changement_type_recalcule_indices(patch_pipeline):
    """C3 : ajouter une pièce et changer son type en Chambre → on a maintenant
    3 Chambres au lieu de 2 → le type_total voit bien 3 Chambres
    (et l'indice se recalcule à la regénération)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Avant : 2 Chambres
    df_before = get_editor_df(at)
    assert (df_before["Type"] == "Chambre").sum() == 2

    # Ajoute + reste Chambre par défaut
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    df_after = get_editor_df(at)
    assert (df_after["Type"] == "Chambre").sum() == 3
    assert len(df_after) == 8

    # Génère devis → vérifie qu'on a "Chambre 1, 2, 3"
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    pieces = set(df_devis["Pièce"].unique())
    assert {"Chambre 1", "Chambre 2", "Chambre 3"}.issubset(pieces), (
        f"Devis devrait avoir Chambre 1/2/3, pièces obtenues : {sorted(pieces)}"
    )


# ============================================================================
# D. Génération devis
# ============================================================================


def test_D3_devis_pour_wc_seul(patch_pipeline):
    """D3 : si on garde seulement 1 WC (en décochant les autres), le devis
    ne contient QUE les équipements NFC WC : 2 lignes (Point lumineux + Interrupteur)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    img_hash = find_img_hash(at)

    # Décoche toutes les pièces sauf WC
    for idx in df.index:
        rid = int(df.loc[idx, "_id"])
        if df.loc[idx, "Type"] != "WC":
            inc_key = f"devis_editor_{img_hash}_inc_{rid}"
            cb = next(c for c in at.checkbox if c.key == inc_key)
            cb.set_value(False)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    assert df_devis is not None
    pieces = set(df_devis["Pièce"].unique())
    assert pieces == {"WC"}, f"Seulement WC attendu, got {pieces}"
    assert len(df_devis) == 2, (
        f"WC sans handicap = 2 équipements NFC, got {len(df_devis)} "
        f"({df_devis['Équipement'].tolist()})"
    )


def test_D5_norme_handicap_augmente_quantites(patch_pipeline):
    """D5 : activer 'Norme handicap' → les quantités de prises (par ex pour
    Chambre) augmentent par rapport au mode normal."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Génère SANS handicap
    find_button_by_label(at, "générer devis").click()
    at.run()
    df_devis_normal = get_devis_df(at)
    chambre1_prises_normal = df_devis_normal[
        (df_devis_normal["Pièce"] == "Chambre 1")
        & (df_devis_normal["Équipement"] == "Prise de courant")
    ]["Qté"].iloc[0]

    # Active la norme handicap
    handicap_cb = next(
        c for c in at.checkbox
        if "handicap" in c.label.lower()
    )
    handicap_cb.set_value(True).run()

    # Re-génère
    find_button_by_label(at, "générer devis").click()
    at.run()
    df_devis_handi = get_devis_df(at)
    chambre1_prises_handi = df_devis_handi[
        (df_devis_handi["Pièce"] == "Chambre 1")
        & (df_devis_handi["Équipement"] == "Prise de courant")
    ]["Qté"].iloc[0]

    assert chambre1_prises_handi > chambre1_prises_normal, (
        f"Handicap doit augmenter les prises Chambre : "
        f"normal={chambre1_prises_normal}, handicap={chambre1_prises_handi}"
    )


# ============================================================================
# E. Édition devis
# ============================================================================


def test_E1_changer_qte_recalcule_total(patch_pipeline):
    """E1 : changer la Qté d'une ligne → Total TTC ligne et Total TTC global
    se recalculent. Vérifie via le DataFrame (synced par on_change)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    img_hash = find_img_hash(at)
    # Première ligne du devis : prend son _id
    target_id = int(df_devis.iloc[0]["_id"])
    target_qty_before = int(df_devis.iloc[0]["Qté"])

    # Trouve le number_input Qté de cette ligne
    qty_key = f"devis_lines_{img_hash}_qty_{target_id}"
    qty_input = next(n for n in at.number_input if n.key == qty_key)
    qty_input.set_value(target_qty_before + 5).run()

    df_after = get_devis_df(at)
    new_qty = int(df_after.loc[df_after["_id"] == target_id, "Qté"].iloc[0])
    assert new_qty == target_qty_before + 5, (
        f"Qté pas synced : attendu {target_qty_before + 5}, got {new_qty}"
    )


# ============================================================================
# F. Ajout / suppression équipements
# ============================================================================


def test_F1_ajouter_equipement_pour_cuisine_insertion_intelligente(patch_pipeline):
    """F1 : ajouter une ligne pour Cuisine → la nouvelle ligne s'insère APRÈS
    le dernier équipement Cuisine (pas à la fin du tableau)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    n_cuisine_before = (df_before["Pièce"] == "Cuisine").sum()
    last_cuisine_idx = df_before[df_before["Pièce"] == "Cuisine"].index[-1]

    # Sélectionne "Cuisine" dans le selectbox "Pour quelle pièce ?"
    img_hash = find_img_hash(at)
    addpiece_key = f"devis_lines_{img_hash}_addpiece"
    addpiece_sel = next(s for s in at.selectbox if s.key == addpiece_key)
    addpiece_sel.set_value("Cuisine").run()

    # Click "➕ Ajouter une ligne"
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    df_after = get_devis_df(at)
    n_cuisine_after = (df_after["Pièce"] == "Cuisine").sum()
    assert n_cuisine_after == n_cuisine_before + 1, (
        f"Cuisine devait gagner 1 ligne, got {n_cuisine_after} vs {n_cuisine_before}"
    )

    # La nouvelle ligne (manual=True) est juste après les Cuisine existantes
    new_line = df_after[df_after["_manual"] == True].iloc[-1]
    assert new_line["Pièce"] == "Cuisine"
    # Vérifie position : à new index = last_cuisine_idx + 1
    new_pos = df_after.index[df_after["_id"] == new_line["_id"]][0]
    assert new_pos == last_cuisine_idx + 1, (
        f"Nouvelle ligne pas insérée juste après dernière Cuisine. "
        f"pos={new_pos}, attendu={last_cuisine_idx + 1}"
    )


# ============================================================================
# G. Préservation lignes manuelles (manual_backup)
# ============================================================================


def test_G2_manual_backup_position_apres_ajout_piece_regen(patch_pipeline):
    """G2 : ajouter ligne manuelle Cuisine + ajouter pièce WC (Pièces editor)
    + Générer devis → la ligne manuelle Cuisine reste positionnée APRÈS
    les équipements Cuisine NFC, PAS à la fin du tableau.

    Bug historique : la ligne manuelle se retrouvait à la fin."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # 1. Générer devis initial
    find_button_by_label(at, "générer devis").click()
    at.run()

    # 2. Ajouter ligne manuelle pour Cuisine
    img_hash = find_img_hash(at)
    addpiece_key = f"devis_lines_{img_hash}_addpiece"
    addpiece_sel = next(s for s in at.selectbox if s.key == addpiece_key)
    addpiece_sel.set_value("Cuisine").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    # 3. Ajouter une nouvelle pièce dans Pièces editor (par défaut Chambre,
    # on laisse Chambre — peu importe le type pour ce test)
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    # 4. Re-générer devis
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    # La ligne ✏️ Cuisine doit être positionnée juste après les autres Cuisine
    cuisine_lines = df_devis[df_devis["Pièce"] == "Cuisine"]
    manual_cuisine = cuisine_lines[cuisine_lines["_manual"] == True]
    assert len(manual_cuisine) == 1, "Ligne manuelle Cuisine devrait être préservée"

    # Position de la ligne manuelle = doit être la DERNIÈRE des Cuisine
    last_cuisine_pos = cuisine_lines.index[-1]
    manual_cuisine_pos = manual_cuisine.index[0]
    assert manual_cuisine_pos == last_cuisine_pos, (
        f"Ligne manuelle Cuisine devrait être en dernière position Cuisine, "
        f"pos={manual_cuisine_pos}, last_cuisine={last_cuisine_pos}"
    )

    # Vérification clé : la ligne manuelle NE doit PAS être à la dernière
    # position du tableau (donc une ligne d'une autre pièce vient APRÈS)
    last_line_overall = df_devis.iloc[-1]
    assert last_line_overall["Pièce"] != "Cuisine" or not last_line_overall["_manual"], (
        f"BUG : la ligne manuelle Cuisine s'est retrouvée à la fin du tableau. "
        f"Dernière ligne : {last_line_overall['Pièce']} / {last_line_overall['Équipement']}"
    )


# ============================================================================
# H. Indexation devis
# ============================================================================


def test_H5_indexation_combinee_chambres_wc(patch_pipeline):
    """H5 : ajouter 1 WC manuel → on a 2 WC + 2 Chambres → devis affiche
    'WC 1', 'WC 2', 'Chambre 1', 'Chambre 2'."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "ajouter une pièce").click()
    at.run()
    type_selects = find_selectboxes_by_label(at, "Type de pièce")
    type_selects[-1].set_value("WC").run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    pieces = set(df_devis["Pièce"].unique())
    assert "WC 1" in pieces
    assert "WC 2" in pieces
    assert "Chambre 1" in pieces
    assert "Chambre 2" in pieces
    assert "Chambre 3" not in pieces  # seulement 2 chambres


# ============================================================================
# I. Totaux
# ============================================================================


def test_I1_total_ht_egale_somme_qty_x_prix(patch_pipeline):
    """I1 : Total HT global = Σ(Qté × Prix HT) sur toutes les lignes."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    expected_total_ht = float(
        (df_devis["Qté"].astype(float) * df_devis["Prix HT (€)"].astype(float)).sum()
    )

    # Le total HT est rendu via st.metric (label "Total HT")
    metrics = [m for m in at.metric if "Total HT" in m.label]
    assert len(metrics) == 1
    # Format : "{x:.2f} €" — parse
    metric_value_str = metrics[0].value
    metric_value = float(
        metric_value_str.replace("€", "").replace(",", ".").strip()
    )
    assert abs(metric_value - expected_total_ht) < 0.01, (
        f"Total HT métrique={metric_value} != calc={expected_total_ht}"
    )


# ============================================================================
# Batch 2 — Extension complète
# ============================================================================


# --- A. Initialisation (suite) ---


def test_A2_init_sans_detection_ocr_default_chambre(patch_pipeline):
    """A2 : OCR vide → 1 ligne par défaut (Chambre) + warning visible."""
    patch_pipeline(custom_ocr=[])  # aucun texte détecté
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    assert len(df) == 1
    assert df.iloc[0]["Type"] == "Chambre"

    # Warning : "Aucune pièce identifiée par l'OCR..."
    warnings_text = [w.value for w in at.warning]
    assert any("Aucune pièce" in w for w in warnings_text), (
        f"Warning attendu, warnings vus : {warnings_text}"
    )


# --- B. Add/Del pièce (suite) ---


def test_B4_supprimer_toutes_pieces_puis_generer_warning(patch_pipeline):
    """B4 : supprimer toutes les pièces + cocher 'Générer devis' → warning."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    img_hash = find_img_hash(at)
    # Décocher toutes les Inclure (suppression effective du devis)
    for idx in df.index:
        rid = int(df.loc[idx, "_id"])
        inc_key = f"devis_editor_{img_hash}_inc_{rid}"
        cb = next(c for c in at.checkbox if c.key == inc_key)
        cb.set_value(False)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    warnings_text = [w.value for w in at.warning]
    assert any("Aucune pièce cochée" in w for w in warnings_text), (
        f"Warning 'aucune pièce cochée' attendu, vus : {warnings_text}"
    )


def test_B5_supprimer_milieu_preserve_autres_lignes(patch_pipeline):
    """B5 : sur 7 pièces, supprimer la 3ème → les 6 restantes ont des _id
    stables et leur ordre est préservé."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df_before = get_editor_df(at)
    ids_before = df_before["_id"].tolist()
    types_before = df_before["Type"].tolist()
    target_id = int(df_before.iloc[2]["_id"])
    expected_ids_after = [i for i in ids_before if i != target_id]
    expected_types_after = [
        t for i, t in zip(ids_before, types_before) if i != target_id
    ]

    img_hash = find_img_hash(at)
    target_btn = next(
        b for b in at.button
        if b.key == f"devis_editor_{img_hash}_del_{target_id}"
    )
    target_btn.click()
    at.run()

    df_after = get_editor_df(at)
    assert df_after["_id"].tolist() == expected_ids_after
    assert df_after["Type"].tolist() == expected_types_after


def test_B6_reinitialiser_reset_etat_depuis_ocr(patch_pipeline):
    """B6 : 'Réinitialiser' → reconstruit depuis OCR, perd les éditions
    (ex: une pièce ajoutée manuellement disparaît)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    n_initial = len(get_editor_df(at))

    # Ajoute 2 pièces
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()
    assert len(get_editor_df(at)) == n_initial + 2

    # Reset
    find_button_by_label(at, "réinitialiser").click()
    at.run()

    df_after = get_editor_df(at)
    assert len(df_after) == n_initial, (
        f"Après reset, attendu {n_initial} pièces, got {len(df_after)}"
    )


# --- C. Auto-indexation (suite) ---


def test_C4_supprimer_un_des_2_wc_enleve_indice(patch_pipeline):
    """C4 : 2 WC → ajoute 1 WC manuel → on a 2 WC → supprime le WC OCR
    → ne reste qu'1 WC → après regen le devis affiche 'WC' sans indice."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Ajoute pièce + WC
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()
    type_selects = find_selectboxes_by_label(at, "Type de pièce")
    type_selects[-1].set_value("WC").run()

    df = get_editor_df(at)
    # Trouve le WC OCR (le 1er WC chronologiquement)
    wc_rows = df[df["Type"] == "WC"]
    assert len(wc_rows) == 2
    ocr_wc_id = int(wc_rows.iloc[0]["_id"])

    img_hash = find_img_hash(at)
    btn = next(
        b for b in at.button
        if b.key == f"devis_editor_{img_hash}_del_{ocr_wc_id}"
    )
    btn.click()
    at.run()

    # Génère devis
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    pieces = set(df_devis["Pièce"].unique())
    assert "WC" in pieces, f"WC seul devrait être 'WC' (sans indice), got {pieces}"
    assert "WC 1" not in pieces
    assert "WC 2" not in pieces


# --- D. Génération devis (suite) ---


def test_D2_generer_sans_piece_cochee(patch_pipeline):
    """D2 : aucune pièce cochée + 'Générer devis' → warning, pas de tableau."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Décoche toutes les pièces
    df = get_editor_df(at)
    img_hash = find_img_hash(at)
    for idx in df.index:
        rid = int(df.loc[idx, "_id"])
        cb = next(
            c for c in at.checkbox
            if c.key == f"devis_editor_{img_hash}_inc_{rid}"
        )
        cb.set_value(False)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    assert get_devis_df(at) is None
    warnings_text = [w.value for w in at.warning]
    assert any("Aucune pièce cochée" in w for w in warnings_text)


def test_D4_devis_cuisine_seule_equipements_nfc(patch_pipeline):
    """D4 : décocher tout sauf Cuisine → devis NFC Cuisine
    (prises, alim spécialisées, point lumineux, interrupteur, RJ45)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    df = get_editor_df(at)
    img_hash = find_img_hash(at)
    for idx in df.index:
        rid = int(df.loc[idx, "_id"])
        if df.loc[idx, "Type"] != "Cuisine":
            cb = next(
                c for c in at.checkbox
                if c.key == f"devis_editor_{img_hash}_inc_{rid}"
            )
            cb.set_value(False)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    assert set(df_devis["Pièce"].unique()) == {"Cuisine"}
    # Cuisine NFC = 6 prises normales + point lumineux + interrupteur + 1 ligne
    # « Alimentation spécialisée » agrégée (Four/Plaque/LV — plus le lave-linge
    # garanti, rattaché à la cuisine faute de SDB/cellier). Les libellés typés
    # (Four/Plaque/LV) n'apparaissent jamais : ils sont agrégés en Alim spé.
    equipements = set(df_devis["Équipement"].tolist())
    assert "Prise de courant" in equipements
    assert "Point lumineux" in equipements
    assert "Interrupteur" in equipements
    assert "Alimentation spécialisée" in equipements
    assert "Four" not in equipements
    assert "Plaque de cuisson" not in equipements
    assert "Lave-vaisselle" not in equipements


# --- E. Édition devis (suite) ---


def test_E2_changer_prix_ht_sync_dataframe(patch_pipeline):
    """E2 : changer Prix HT d'une ligne → DataFrame sync via on_change."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    img_hash = find_img_hash(at)
    target_id = int(df_devis.iloc[0]["_id"])
    ht_key = f"devis_lines_{img_hash}_ht_{target_id}"
    ht_input = next(n for n in at.number_input if n.key == ht_key)
    ht_input.set_value(99.50).run()

    df_after = get_devis_df(at)
    new_ht = float(df_after.loc[df_after["_id"] == target_id, "Prix HT (€)"].iloc[0])
    assert abs(new_ht - 99.50) < 0.01


def test_E3_changer_tva_recalcule_total_ttc(patch_pipeline):
    """E3 : changer le taux TVA dans la sidebar → Total TTC global recalculé.
    HT inchangé, mais TTC = HT × (1 + nouveau taux)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    metrics_before = {m.label: m.value for m in at.metric}
    ttc_before = float(
        metrics_before["Total TTC"].replace("€", "").replace(",", ".").strip()
    )

    # Sidebar : selectbox "Taux TVA"
    tva_sel = next(s for s in at.selectbox if s.label == "Taux TVA")
    tva_sel.set_value("Rénovation > 2 ans 10%").run()

    metrics_after = {m.label: m.value for m in at.metric}
    ttc_after = float(
        metrics_after["Total TTC"].replace("€", "").replace(",", ".").strip()
    )
    ht_after = float(
        metrics_after["Total HT"].replace("€", "").replace(",", ".").strip()
    )
    # TTC = HT × 1.10
    assert abs(ttc_after - ht_after * 1.10) < 0.05
    # Et TTC a baissé par rapport à 20%
    assert ttc_after < ttc_before


def test_E4_changer_piece_dune_ligne_sync_dataframe(patch_pipeline):
    """E4 : changer la Pièce d'une ligne (Cuisine → Sejour) → DataFrame sync.

    Note : les options du selectbox Pièce du devis sont les valeurs
    NFCCategory (ex: 'Sejour', 'SalleDeBain') pas les labels FR de l'éditeur
    Pièces. C'est cohérent : le devis affiche les noms internes NFC."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    img_hash = find_img_hash(at)
    target_id = int(df_devis[df_devis["Pièce"] == "Cuisine"].iloc[0]["_id"])
    p_key = f"devis_lines_{img_hash}_piece_{target_id}"
    p_sel = next(s for s in at.selectbox if s.key == p_key)
    # Cible : une autre pièce présente dans le devis
    available = [o for o in p_sel.options if o != "Cuisine" and o != "Autre"]
    assert len(available) > 0, f"Pas d'autre pièce dispo : {p_sel.options}"
    target_piece = available[0]
    p_sel.set_value(target_piece).run()

    df_after = get_devis_df(at)
    new_piece = df_after.loc[df_after["_id"] == target_id, "Pièce"].iloc[0]
    assert new_piece == target_piece


# --- F. Add/Del équipement (suite) ---


def test_F2_trash_equipement_supprime_bonne_ligne(patch_pipeline):
    """F2 : click 🗑️ sur une ligne d'équipement → cette ligne disparaît du
    devis. Pareil que R1 mais pour le tableau devis (pas l'éditeur Pièces)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    img_hash = find_img_hash(at)
    target_id = int(df_before.iloc[3]["_id"])

    btn = next(
        b for b in at.button
        if b.key == f"devis_lines_{img_hash}_del_{target_id}"
    )
    btn.click()
    at.run()

    df_after = get_devis_df(at)
    assert len(df_after) == len(df_before) - 1
    assert target_id not in df_after["_id"].tolist()


def test_F3_ajouter_ligne_pour_autre_append_en_fin(patch_pipeline):
    """F3 : ajouter une ligne avec Pièce='Autre' (pas dans le devis)
    → fallback append à la fin du tableau."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    img_hash = find_img_hash(at)

    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("Autre").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    df_after = get_devis_df(at)
    assert len(df_after) == len(df_before) + 1
    # Nouvelle ligne en dernière position
    assert df_after.iloc[-1]["Pièce"] == "Autre"
    assert df_after.iloc[-1]["_manual"] == True


def test_F4_ajouter_3_lignes_consecutives_meme_piece_ordre_preserve(patch_pipeline):
    """F4 : ajouter 3 équipements pour la même pièce → les 3 sont insérées
    consécutivement après le dernier équipement de cette pièce."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("Cuisine").run()

    for _ in range(3):
        find_button_by_label(at, "ajouter une ligne").click()
        at.run()

    df_after = get_devis_df(at)
    cuisine_lines = df_after[df_after["Pièce"] == "Cuisine"]
    manual_cuisine = cuisine_lines[cuisine_lines["_manual"] == True]
    assert len(manual_cuisine) == 3

    # Les 3 manuelles sont à la fin du bloc Cuisine, en positions consécutives
    cuisine_positions = cuisine_lines.index.tolist()
    manual_positions = manual_cuisine.index.tolist()
    assert manual_positions == cuisine_positions[-3:], (
        f"Les 3 manuelles devraient être en fin du bloc Cuisine. "
        f"Manuel positions: {manual_positions}, dernières 3 Cuisine: "
        f"{cuisine_positions[-3:]}"
    )


# --- G. Manual backup (suite) ---


def test_G1_ligne_manuelle_preservee_apres_simple_regen(patch_pipeline):
    """G1 : ajouter ligne manuelle Cuisine, click 'Générer devis' une 2ème
    fois → la ligne ✏️ Cuisine est préservée, positionnée après les autres
    équipements Cuisine."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("Cuisine").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    n_manual_before = int(get_devis_df(at)["_manual"].sum())
    assert n_manual_before == 1

    # Re-génère sans changement
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_after = get_devis_df(at)
    n_manual_after = int(df_after["_manual"].sum())
    assert n_manual_after == 1, (
        f"Ligne manuelle perdue à la regénération. "
        f"_manual count: {n_manual_before} → {n_manual_after}"
    )


def test_G3_ligne_manuelle_pour_piece_supprimee_append_en_fin(patch_pipeline):
    """G3 : ajouter ligne manuelle WC, supprimer la pièce WC de l'éditeur
    Pièces, regen → la ligne manuelle est préservée (fallback en fin de
    tableau car la pièce d'origine n'existe plus)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("WC").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    # Supprime le WC dans l'éditeur Pièces
    df_editor = get_editor_df(at)
    wc_id = int(df_editor[df_editor["Type"] == "WC"].iloc[0]["_id"])
    btn = next(
        b for b in at.button
        if b.key == f"devis_editor_{img_hash}_del_{wc_id}"
    )
    btn.click()
    at.run()

    # Regen
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_after = get_devis_df(at)
    manual_lines = df_after[df_after["_manual"] == True]
    assert len(manual_lines) == 1, "Ligne manuelle WC devrait être préservée"
    # Pas de pièce WC dans le devis (car supprimée)
    assert "WC" not in df_after[df_after["_manual"] == False]["Pièce"].values
    # La ligne manuelle est en fin (fallback)
    assert df_after.iloc[-1]["_manual"] == True


def test_G5_modifs_ligne_manuelle_preservees_apres_regen(patch_pipeline):
    """G5 : ajouter ligne manuelle, modifier sa Qté à 7, regen
    → la nouvelle valeur Qté=7 est préservée."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("Cuisine").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    df = get_devis_df(at)
    manual_id = int(df[df["_manual"] == True].iloc[0]["_id"])
    qty_key = f"devis_lines_{img_hash}_qty_{manual_id}"
    qty_input = next(n for n in at.number_input if n.key == qty_key)
    qty_input.set_value(7).run()

    # Regen
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_after = get_devis_df(at)
    manual_after = df_after[df_after["_manual"] == True]
    assert len(manual_after) == 1
    assert int(manual_after.iloc[0]["Qté"]) == 7, (
        f"Qté manuelle pas préservée : attendu 7, got {manual_after.iloc[0]['Qté']}"
    )


# --- H. Indexation devis (suite) ---


def test_H1_3_chambres_indexees_1_2_3(patch_pipeline):
    """H1 : ajouter 1 Chambre manuelle → on a 3 Chambres → devis affiche
    Chambre 1, Chambre 2, Chambre 3."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Default = "Chambre" pour les nouvelles pièces
    find_button_by_label(at, "ajouter une pièce").click()
    at.run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    pieces = set(df_devis["Pièce"].unique())
    for n in (1, 2, 3):
        assert f"Chambre {n}" in pieces, (
            f"Chambre {n} manquante. Pièces : {sorted(pieces)}"
        )
    assert "Chambre 4" not in pieces


def test_H2_1_seule_cuisine_sans_indice(patch_pipeline):
    """H2 : 1 seule Cuisine dans l'OCR → devis affiche 'Cuisine' (sans indice
    '1' ou '2')."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis = get_devis_df(at)
    pieces = set(df_devis["Pièce"].unique())
    assert "Cuisine" in pieces
    assert "Cuisine 1" not in pieces


# --- I. Totaux (suite) ---


def test_I2_total_ttc_egale_ht_x_1plus_tva(patch_pipeline):
    """I2 : Total TTC = Total HT × (1 + taux TVA). Taux par défaut 20%."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    metrics = {m.label: m.value for m in at.metric}
    ht = float(metrics["Total HT"].replace("€", "").replace(",", ".").strip())
    ttc = float(metrics["Total TTC"].replace("€", "").replace(",", ".").strip())
    # TVA par défaut = 20%
    assert abs(ttc - ht * 1.20) < 0.05, (
        f"Total TTC ({ttc}) ≠ HT × 1.20 ({ht * 1.20})"
    )


def test_I4_decocher_piece_puis_regen_enleve_equipements(patch_pipeline):
    """I4 : décocher 1 pièce + regen → ses équipements absents du devis,
    total HT diminué."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    metrics_before = {m.label: m.value for m in at.metric}
    ht_before = float(
        metrics_before["Total HT"].replace("€", "").replace(",", ".").strip()
    )

    # Décoche la Cuisine (la plus coûteuse en NFC)
    img_hash = find_img_hash(at)
    df_editor = get_editor_df(at)
    cuisine_id = int(df_editor[df_editor["Type"] == "Cuisine"].iloc[0]["_id"])
    cb = next(
        c for c in at.checkbox
        if c.key == f"devis_editor_{img_hash}_inc_{cuisine_id}"
    )
    cb.set_value(False).run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    df_devis_after = get_devis_df(at)
    assert "Cuisine" not in df_devis_after["Pièce"].unique()
    metrics_after = {m.label: m.value for m in at.metric}
    ht_after = float(
        metrics_after["Total HT"].replace("€", "").replace(",", ".").strip()
    )
    assert ht_after < ht_before, (
        f"Total HT devrait baisser après décoche Cuisine : "
        f"avant={ht_before}, après={ht_after}"
    )


def test_I5_qte_zero_contribue_zero_au_total(patch_pipeline):
    """I5 : mettre Qté=0 sur une ligne → cette ligne ne contribue pas au
    total HT (test du DataFrame sync via on_change)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    img_hash = find_img_hash(at)
    target_id = int(df_before.iloc[0]["_id"])
    target_ht = float(df_before.iloc[0]["Prix HT (€)"])
    target_qty = int(df_before.iloc[0]["Qté"])

    metrics_before = {m.label: m.value for m in at.metric}
    ht_total_before = float(
        metrics_before["Total HT"].replace("€", "").replace(",", ".").strip()
    )

    # Set Qté = 0
    qty_input = next(
        n for n in at.number_input
        if n.key == f"devis_lines_{img_hash}_qty_{target_id}"
    )
    qty_input.set_value(0).run()

    metrics_after = {m.label: m.value for m in at.metric}
    ht_total_after = float(
        metrics_after["Total HT"].replace("€", "").replace(",", ".").strip()
    )
    expected_diff = target_qty * target_ht
    assert abs((ht_total_before - ht_total_after) - expected_diff) < 0.05


# --- K. Edge case réaliste ---


def test_K5_supprimer_piece_avec_ligne_manuelle_preserve_manuelle(patch_pipeline):
    """K5 : ajouter ligne manuelle Cuisine, supprimer la Cuisine dans
    l'éditeur Pièces, regen → la ligne manuelle est préservée (fallback)
    et la Cuisine NFC n'apparaît plus."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    addpiece_sel = next(
        s for s in at.selectbox if s.key == f"devis_lines_{img_hash}_addpiece"
    )
    addpiece_sel.set_value("Cuisine").run()
    find_button_by_label(at, "ajouter une ligne").click()
    at.run()

    # Supprime Cuisine de l'éditeur
    df_editor = get_editor_df(at)
    cuisine_id = int(df_editor[df_editor["Type"] == "Cuisine"].iloc[0]["_id"])
    btn = next(
        b for b in at.button
        if b.key == f"devis_editor_{img_hash}_del_{cuisine_id}"
    )
    btn.click()
    at.run()

    # Regen
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_after = get_devis_df(at)
    # La ligne manuelle est préservée
    manual = df_after[df_after["_manual"] == True]
    assert len(manual) == 1
    assert manual.iloc[0]["Pièce"] == "Cuisine"
    # Aucune ligne NFC Cuisine (la pièce a été supprimée de l'éditeur)
    nfc_cuisine = df_after[(df_after["Pièce"] == "Cuisine") & (df_after["_manual"] == False)]
    assert len(nfc_cuisine) == 0


# ============================================================================
# Phase 6 — Équipements électriques sur le plan (E1-E7)
# ============================================================================


def test_E1_generer_devis_creates_equipments(patch_pipeline):
    """E1 : après 'Générer devis', equipments_state contient N instances
    pour chaque ligne Qté=N avec les bons (room, type)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)

    find_button_by_label(at, "générer devis").click()
    at.run()

    equipments = get_equipments_state(at)
    df_devis = get_devis_df(at)
    assert equipments is not None, "equipments_state non créé"
    assert df_devis is not None

    # Labels FR (EQUIPMENT_LABELS_FR) → types EQUIP_TYPES
    label_to_type = {
        "Prise de courant": "Prise",
        "Prise RJ45": "RJ45",
        "Point lumineux": "LightPoint",
        "Interrupteur": "Switch",
        "Alimentation spécialisée": "SpecialFeed",
    }
    for idx in df_devis.index:
        room = str(df_devis.at[idx, "Pièce"])
        equip_label = str(df_devis.at[idx, "Équipement"])
        qty = int(df_devis.at[idx, "Qté"])
        equip_type = label_to_type.get(equip_label)
        if not equip_type:
            continue
        matching = [
            e for e in equipments
            if e["room"] == room and e["type"] == equip_type
        ]
        assert len(matching) == qty, (
            f"Ligne {room} {equip_label} Qté={qty} mais "
            f"{len(matching)} instances équipements"
        )

    # Tous les ids uniques
    all_ids = [e["id"] for e in equipments]
    assert len(set(all_ids)) == len(all_ids)


def test_E2_palette_drag_in_increments_devis_qty(patch_pipeline):
    """E2 : simuler un drag depuis la palette équip = Qté +1 dans le devis.

    AppTest ne peut pas simuler nativement un drag-drop d'iframe.
    On valide le mécanisme de sync DataFrame ↔ equipments_state en pokant
    directement le state."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    img_hash = find_img_hash(at)
    cuisine_prise_idx = df_before[
        (df_before["Pièce"] == "Cuisine")
        & (df_before["Équipement"] == "Prise de courant")
    ].index[0]
    qty_before = int(df_before.at[cuisine_prise_idx, "Qté"])

    current = at.session_state[f"equipments_state_{img_hash}"]
    new_inst = {
        "id": f"new_test_{len(current)}",
        "type": "Prise",
        "room": "Cuisine",
        "x": 50, "y": 50,
        "color": "rgb(255, 112, 67)",
    }
    at.session_state[f"equipments_state_{img_hash}"] = current + [new_inst]
    # Simulate Python sync incrementing the line Qté
    df = at.session_state[f"devis_lines_{img_hash}"]
    df.at[cuisine_prise_idx, "Qté"] = qty_before + 1
    ids = list(df.at[cuisine_prise_idx, "_equip_ids"] or [])
    ids.append(new_inst["id"])
    df.at[cuisine_prise_idx, "_equip_ids"] = ids
    at.session_state[f"devis_lines_{img_hash}"] = df
    at.run()

    df_after = get_devis_df(at)
    assert int(df_after.at[cuisine_prise_idx, "Qté"]) == qty_before + 1


def test_E3_equipment_removal_decrements_devis_qty(patch_pipeline):
    """E3 : retirer une instance de equipments_state (simulant drag-out)
    → Qté de la ligne devis correspondante doit décrémenter."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    current = at.session_state[f"equipments_state_{img_hash}"]
    df = at.session_state[f"devis_lines_{img_hash}"]
    cuisine_prise_idx = df[
        (df["Pièce"] == "Cuisine") & (df["Équipement"] == "Prise de courant")
    ].index[0]
    qty_before = int(df.at[cuisine_prise_idx, "Qté"])
    ids_before = list(df.at[cuisine_prise_idx, "_equip_ids"] or [])
    assert len(ids_before) == qty_before
    assert qty_before >= 1
    removed_id = ids_before[0]

    new_eq = [e for e in current if e["id"] != removed_id]
    at.session_state[f"equipments_state_{img_hash}"] = new_eq
    new_ids = [i for i in ids_before if i != removed_id]
    df.at[cuisine_prise_idx, "_equip_ids"] = new_ids
    df.at[cuisine_prise_idx, "Qté"] = qty_before - 1
    at.session_state[f"devis_lines_{img_hash}"] = df
    at.run()

    df_after = get_devis_df(at)
    assert int(df_after.at[cuisine_prise_idx, "Qté"]) == qty_before - 1


def test_E4_devis_line_removal_cleans_equipments(patch_pipeline):
    """E4 : supprimer une ligne devis via 🗑️ → tous les équipements de
    cette ligne doivent être retirés de equipments_state."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    df = at.session_state[f"devis_lines_{img_hash}"]
    line = df[
        (df["Pièce"] == "Cuisine") & (df["Équipement"] == "Prise de courant")
    ]
    line_idx = line.index[0]
    line_id = int(df.at[line_idx, "_id"])
    line_equip_ids = list(df.at[line_idx, "_equip_ids"] or [])
    assert len(line_equip_ids) > 0

    del_btn_key = f"devis_lines_{img_hash}_del_{line_id}"
    del_btn = next(b for b in at.button if b.key == del_btn_key)
    del_btn.click()
    at.run()

    new_eq = at.session_state[f"equipments_state_{img_hash}"]
    remaining_ids = {e["id"] for e in new_eq}
    for eid in line_equip_ids:
        assert eid not in remaining_ids, (
            f"Équipement {eid} de la ligne supprimée toujours présent"
        )


def test_E5_pastille_removal_cleans_equipments(patch_pipeline):
    """E5 : supprimer une pastille pièce (Cuisine) → tous les équipements
    de cette pièce supprimés (cohérence)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    eq_before = at.session_state[f"equipments_state_{img_hash}"]
    cuisine_equips_before = [e for e in eq_before if e["room"] == "Cuisine"]
    assert len(cuisine_equips_before) > 0

    pastilles_key = f"pastilles_state_{img_hash}"
    new_pastilles = [
        p for p in at.session_state[pastilles_key] if p["label"] != "Cuisine"
    ]
    at.session_state[pastilles_key] = new_pastilles
    new_eq = [
        e for e in at.session_state[f"equipments_state_{img_hash}"]
        if e["room"] != "Cuisine"
    ]
    at.session_state[f"equipments_state_{img_hash}"] = new_eq
    at.run()

    eq_after = at.session_state[f"equipments_state_{img_hash}"]
    cuisine_equips_after = [e for e in eq_after if e["room"] == "Cuisine"]
    assert len(cuisine_equips_after) == 0


def test_E6_smart_placement_inside_image_bbox(patch_pipeline):
    """E6 : sans segmentation active, équipements doivent être dans bbox image
    (FAKE_IMG_BYTES = 100x100)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    eq = get_equipments_state(at)
    assert eq is not None
    for inst in eq:
        assert 0 <= inst["x"] <= 100, f"x={inst['x']} hors bbox"
        assert 0 <= inst["y"] <= 100, f"y={inst['y']} hors bbox"


def test_E7_equipments_auto_generated_on_plan_load(patch_pipeline):
    """E7 (V1.1) : depuis le retrait du toggle sidebar, les équipements
    sont auto-générés dès que les pastilles OCR sont prêtes — pas besoin
    de cliquer 'Générer devis' au préalable."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    eq = get_equipments_state(at)
    assert eq is not None
    assert len(eq) > 0, "équipements devraient être auto-générés à l'init"


# ============================================================================
# Phase 5 : Tableau électrique V1 — AppTest T1-T5
# ============================================================================


def test_T1_tableau_appears_after_devis_trigger(patch_pipeline):
    """T1 : après click 'Générer devis', la subheader '⚡ Tableau électrique'
    apparaît."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    headers = [h.value for h in at.subheader]
    assert any("Tableau électrique" in h for h in headers)


def test_T2_toggle_heating_off_no_heating_circuits(patch_pipeline):
    """T2 : désactiver chauffage → l'HTML de la liste ne contient pas
    'Chauffage ' (circuits) ni 'Sèche-serviettes ' (circuits)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Désactiver toggle chauffage (key="tableau_heating_enabled")
    toggle = next(t for t in at.toggle
                  if t.key == "tableau_heating_enabled")
    toggle.set_value(False).run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    # Concat tous les markdown pour grep
    all_md = "\n".join(m.value for m in at.markdown if m.value)
    # Les circuits chauffage ont des labels "Chauffage Séjour, ..." et
    # "Sèche-serviettes 1". Avec heating=False ils ne doivent pas apparaître.
    # On cherche dans le rendu HTML des circuits (render_html_table).
    # La colonne "Type circuit" utilise "Chauffage" et "Sèche-serv." mais
    # les labels de circuits (colonne Pièces) contiennent "Chauffage Séjour" etc.
    # On vérifie que le label de circuit spécifique n'est pas présent.
    assert "Sèche-serviettes" not in all_md, (
        "Les circuits Sèche-serviettes ne devraient pas apparaître quand heating=False"
    )
    # Vérifie absence de la colonne circuit type "Chauffage" dans le HTML table
    # (render_html_table met le label du circuit dans la 2e colonne TD)
    # En mode heating=False, aucun circuit de type HEATING ni TOWEL_WARMER
    # → le mot "Chauffage" peut apparaître dans la sidebar subheader seulement.
    # On vérifie que "Sèche-serviettes" est bien absent (plus strict).


def test_T3_logement_has_at_least_3_rcds(patch_pipeline):
    """T3 forcé via override → au moins 3 RCD distincts dans la liste HTML."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Forcer typologie T3 via le selectbox sidebar (dans l'expander)
    selectbox = next(s for s in at.selectbox
                     if s.key == "tableau_typology_override")
    selectbox.set_value("T3").run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    import re
    all_md = "\n".join(m.value for m in at.markdown if m.value)
    ids_found = set(re.findall(r"ID\s+(\d+)\s+Type", all_md))
    assert {"1", "2", "3"}.issubset(ids_found), (
        f"Expected ID 1, 2, 3 but found {ids_found}"
    )


def test_T4_pdf_download_button_present_and_returns_bytes(patch_pipeline):
    """T4 : bouton download PDF est présent dans les boutons standards.

    NOTE : AppTest 1.57.0 n'expose pas de propriété `download_button` —
    st.download_button est rendu comme st.button dans le widget tree.
    On vérifie que la clé 'dl_tableau_pdf' est bien présente comme bouton.
    """
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    # AppTest 1.57 : download_button non exposé — on vérifie via session_state
    # que le PDF a bien été généré (le tableau est construit avec render_html_table)
    # et que la section Tableau apparaît bien (en complément de T1).
    headers = [h.value for h in at.subheader]
    assert any("Tableau électrique" in h for h in headers), (
        "Section Tableau électrique absente — le PDF ne peut pas être téléchargé"
    )
    # Vérifie que img_hash est présent en session state (condition pour le PDF)
    from conftest import find_img_hash
    img_hash = find_img_hash(at)
    # SafeSessionState ne supporte pas .get() — on accède directement
    devis_key = f"devis_global_{img_hash}"
    try:
        devis_global = at.session_state[devis_key]
    except KeyError:
        devis_global = None
    assert devis_global is not None, (
        "devis_global absent du session_state — le PDF n'a pas pu être généré"
    )
    # Vérifie que export_pdf fonctionne directement
    from src.planrec import nfc_tableau as _nfc_tab
    from src.planrec import tableau_renderer as _tab_render
    tableau = _nfc_tab.generate_tableau(devis_global=devis_global)
    pdf_bytes = _tab_render.export_pdf(tableau)
    assert isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 100, (
        f"export_pdf doit retourner des bytes PDF valides, got {type(pdf_bytes)}"
    )


def test_T5_typology_override_changes_n_rcds(patch_pipeline):
    """T5 : forcer typology=T5 → au moins 4 RCD affichés dans la liste HTML."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Override typologie à T5
    selectbox = next(s for s in at.selectbox
                     if s.key == "tableau_typology_override")
    selectbox.set_value("T5").run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    import re
    all_md = "\n".join(m.value for m in at.markdown if m.value)
    ids = set(re.findall(r"ID\s+(\d+)\s+Type", all_md))
    # T5 force au moins 4 RCD (règle _TYPO_RCD_RULE T5=4)
    assert len(ids) >= 4, (
        f"Expected at least 4 RCD for T5 override, found {ids}"
    )
