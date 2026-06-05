"""Rendu PDF visuel d'une Facture via reportlab (A4 portrait FR)."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from src.facturation.models import Facture, FactureType
from src.facturation.pdf.styles import BATIA_BLUE, MARGIN, PAGE_SIZE, get_styles
from src.facturation.services.totals import compute_facture_totals


_TITRE_TYPE = {
    "380": "FACTURE",
    "386": "FACTURE D'ACOMPTE",
    "326": "FACTURE DE SITUATION",
    "381": "AVOIR",
}


def _type_value(facture_type) -> str:
    """Normalise FactureType (SQLite peut renvoyer str)."""
    if hasattr(facture_type, "value"):
        return facture_type.value
    return str(facture_type)


def _client_type_value(client_type) -> str:
    if hasattr(client_type, "value"):
        return client_type.value
    return str(client_type)


def render_facture_pdf(facture: Facture) -> bytes:
    """Renvoie le PDF (bytes) au format A4 portrait, mentions légales FR."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    styles = get_styles()
    story = []

    a = facture.artisan
    c = facture.client

    seller_block = [
        f"<b>{a.raison_sociale}</b>",
        f"{a.adresse_rue}",
        f"{a.adresse_cp} {a.adresse_ville}, {a.adresse_pays}",
        f"SIRET : {a.siret} — TVA : {a.numero_tva_intra}",
        f"{a.email}" + (f" — {a.telephone}" if a.telephone else ""),
    ]
    seller_para = Paragraph("<br/>".join(seller_block), styles["body"])

    type_label = _TITRE_TYPE.get(_type_value(facture.type), "FACTURE")
    title_para = Paragraph(
        f"<b>{type_label}</b><br/>N° {facture.numero}",
        styles["title"],
    )

    header_tbl = Table(
        [[seller_para, title_para]],
        colWidths=[doc.width * 0.55, doc.width * 0.45],
    )
    header_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header_tbl)
    story.append(Spacer(1, 6 * mm))

    client_block = [
        "<b>Destinataire</b>",
        f"{c.nom_ou_raison}",
        f"{c.adresse_rue}",
        f"{c.adresse_cp} {c.adresse_ville}, {c.adresse_pays}",
    ]
    if c.siret:
        client_block.append(f"SIRET : {c.siret}")

    meta_block = [
        f"<b>Date</b> : {facture.date_emission.strftime('%d/%m/%Y')}",
        f"<b>Échéance</b> : {facture.date_echeance.strftime('%d/%m/%Y')}",
    ]
    if facture.reference_devis:
        meta_block.append(f"<b>Réf. devis</b> : {facture.reference_devis}")
    if facture.motif_avoir:
        meta_block.append(f"<b>Motif</b> : {facture.motif_avoir}")

    info_tbl = Table(
        [[Paragraph("<br/>".join(client_block), styles["body"]),
          Paragraph("<br/>".join(meta_block), styles["body"])]],
        colWidths=[doc.width * 0.55, doc.width * 0.45],
    )
    info_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("INNERPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 4 * mm))

    if facture.objet:
        story.append(Paragraph(f"<b>Objet</b> : {facture.objet}", styles["body"]))
        story.append(Spacer(1, 4 * mm))

    rows = [["#", "Désignation", "Qté", "Unité", "PU HT (€)", "TVA", "HT (€)"]]
    for l in facture.lignes:
        unite = l.unite.value if hasattr(l.unite, "value") else str(l.unite)
        rows.append([
            str(l.ordre), l.designation, f"{l.quantite:.2f}",
            unite, f"{l.prix_unitaire_ht:.2f}",
            f"{l.taux_tva:.0f}%", f"{l.montant_ht_ligne:.2f}",
        ])
    table = Table(rows, colWidths=[10*mm, doc.width - 110*mm, 15*mm, 15*mm, 25*mm, 15*mm, 30*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BATIA_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    totals = compute_facture_totals(facture.lignes)
    totaux_rows = [
        ["Total HT", f"{totals['montant_ht']:.2f} €"],
    ]
    for taux, vals in totals["par_taux"].items():
        totaux_rows.append([f"TVA {taux:.0f}% (base {vals['base_ht']:.2f})",
                            f"{vals['tva']:.2f} €"])
    totaux_rows.append(["Total TTC", f"{totals['montant_ttc']:.2f} €"])
    if facture.acompte_montant_ht and facture.acompte_montant_ht > 0:
        totaux_rows.append(["Acomptes déjà versés (HT)",
                            f"{facture.acompte_montant_ht:.2f} €"])
    totaux_rows.append(["NET À PAYER", f"{facture.montant_du_ttc:.2f} €"])
    totaux_tbl = Table(totaux_rows, colWidths=[doc.width * 0.6, doc.width * 0.4])
    totaux_tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f0fe")),
        ("BOX", (0, -1), (-1, -1), 1, BATIA_BLUE),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(totaux_tbl)
    story.append(Spacer(1, 4 * mm))

    if facture.conditions_paiement:
        story.append(Paragraph(f"<b>Conditions de paiement</b> : "
                               f"{facture.conditions_paiement}", styles["body"]))
    rib_lines = [f"<b>IBAN</b> : {a.iban}"]
    if a.bic:
        rib_lines.append(f"<b>BIC</b> : {a.bic}")
    if a.nom_banque:
        rib_lines.append(f"<b>Banque</b> : {a.nom_banque}")
    story.append(Paragraph("<br/>".join(rib_lines), styles["body"]))
    story.append(Spacer(1, 4 * mm))

    mentions = [
        ("Pénalités de retard : taux d'intérêt légal majoré de 10 points + "
         "indemnité forfaitaire de 40 € (art. L441-10 Code de commerce)."),
        ("Pas d'escompte pour règlement anticipé."),
    ]
    if a.mentions_assurance_decennale:
        mentions.append(f"Assurance décennale : {a.mentions_assurance_decennale}")
    if a.mentions_garantie_biennale:
        mentions.append(f"Garantie biennale : {a.mentions_garantie_biennale}")
    if _client_type_value(c.type) == "particulier":
        mentions.append("Médiation de la consommation : conformément aux art. L611-1 à L611-4 "
                        "Code de la consommation, vous pouvez recourir à un médiateur.")

    story.append(Paragraph("<br/>".join(mentions), styles["small"]))

    doc.build(story)
    return buf.getvalue()
