"""Rendu visuel du Tableau électrique : SVG inline (Streamlit st.markdown) +
liste HTML descriptive + export PDF A4 (reportlab).

Aucun import Streamlit ou React — module testable pytest seul.
"""
from __future__ import annotations

from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType


# Couleurs par fonction de circuit (cohérent palette équipements)
CIRCUIT_COLORS: dict[CircuitType, str] = {
    CircuitType.LIGHTING:        "#FFD54F",  # jaune
    CircuitType.SOCKET:          "#42A5F5",  # bleu
    CircuitType.KITCHEN_SPECIAL: "#AB47BC",  # violet
    CircuitType.LAUNDRY:         "#FF7043",  # orange
    CircuitType.BOILER:          "#C62828",  # rouge sombre
    CircuitType.HEATING:         "#EF5350",  # rouge clair
    CircuitType.TOWEL_WARMER:    "#EF9A9A",  # rose clair
    CircuitType.KITCHEN_SOCKET:  "#1E88E5",  # bleu soutenu (prises cuisine 20A)
    CircuitType.VMC:             "#78909C",  # gris bleuté
    CircuitType.HEAT_PUMP:       "#00897B",  # teal (PAC)
    CircuitType.EV_CHARGER:      "#3949AB",  # indigo (borne)
}


# Dimensions SVG (cf. spec section 5)
MODULE_W = 60
MODULE_H = 100
RCD_BLOCK_W = 240  # 4 modules de large
RCD_AVAILABLE_SLOTS = 18  # max modules par rangée


def render_svg(tableau: Tableau) -> str:
    """Génère le SVG complet du tableau comme string XML.

    Sortie embarquable dans `st.markdown(svg_xml, unsafe_allow_html=True)`.
    """
    if not tableau.rcds:
        return '<div style="padding:1em;color:#888">Aucun circuit à afficher.</div>'

    n_rcds = len(tableau.rcds)
    width = RCD_BLOCK_W + RCD_AVAILABLE_SLOTS * MODULE_W
    height = n_rcds * MODULE_H + 30  # 30 px header

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'style="background:#FAFAFA; font-family:Inter,sans-serif">',
        f'<text x="10" y="20" font-size="14" font-weight="bold">'
        f'Tableau électrique — Logement {tableau.typology}</text>',
    ]

    for i, rcd in enumerate(tableau.rcds):
        y = 30 + i * MODULE_H
        parts.append(_render_rcd_row(rcd, y, idx=i + 1))

    parts.append('</svg>')
    return "".join(parts)


def _render_rcd_row(rcd: RCD, y: int, idx: int) -> str:
    """Une rangée RCD = bloc ID + N modules disjoncteur.

    `idx` = numéro séquentiel 1-based pour cross-référencer avec la table
    de détail des circuits ('ID 1', 'ID 2', ...).
    """
    parts: list[str] = []

    # Bloc RCD (gauche, fond blanc bord noir épais)
    parts.append(
        f'<rect x="0" y="{y}" width="{RCD_BLOCK_W}" height="{MODULE_H}" '
        f'fill="white" stroke="#000" stroke-width="2"/>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 22}" font-size="13" '
        f'font-weight="bold" text-anchor="middle">ID {idx}</text>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 40}" font-size="11" '
        f'text-anchor="middle">{rcd.amps} A · Type {rcd.rcd_type}</text>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 58}" font-size="10" '
        f'text-anchor="middle">{rcd.sensitivity_ma} mA</text>'
    )

    # Modules disjoncteur (droite)
    for j, circuit in enumerate(rcd.circuits):
        x = RCD_BLOCK_W + j * MODULE_W
        parts.append(_render_module(circuit, x, y))

    return "".join(parts)


def _tokenize_hyphen(label: str) -> list[str]:
    """Split sur espaces puis sur traits d'union en gardant le tiret collé au
    token précédent ("Sèche-serviettes" → ["Sèche-", "serviettes"])."""
    words: list[str] = []
    for raw in label.split():
        parts = raw.split("-")
        for i, p in enumerate(parts):
            if not p:
                continue
            words.append(p + "-" if i < len(parts) - 1 else p)
    return words


def _wrap_label(label: str, max_chars_per_line: int = 9, max_lines: int = 3) -> list[str]:
    """Découpe un label en lignes de ≤ max_chars_per_line, en coupant aux espaces
    ET aux traits d'union (évite que "Sèche-serviettes" dépasse du module).
    Si le dernier mot ne tient pas après max_lines, le dernier mot est tronqué avec …
    Les mots individuels plus longs que max_chars_per_line restent sur leur propre
    ligne (overflow gracieux plutôt que coupure intra-mot)."""
    words = _tokenize_hyphen(label)
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars_per_line:
            current = current + " " + word
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        last = lines[-1]
        lines[-1] = (last[:max_chars_per_line - 1] + "…") if len(last) >= max_chars_per_line else last + "…"
    return lines


def _render_module(circuit: Circuit, x: int, y: int) -> str:
    """Un module disjoncteur."""
    color = CIRCUIT_COLORS.get(circuit.type, "#CCCCCC")
    type_a_marker = "*" if circuit.requires_type_a else ""
    label_lines = _wrap_label(circuit.label, max_chars_per_line=9, max_lines=3)

    # Placement vertical adapté au nombre de lignes (zone label : y+35 à y+72)
    n = len(label_lines)
    if n == 1:
        line_ys = [y + 55]
    elif n == 2:
        line_ys = [y + 48, y + 60]
    else:  # 3
        line_ys = [y + 42, y + 54, y + 66]

    label_svg = "".join(
        f'<text x="{x + MODULE_W // 2}" y="{ly}" font-size="9" '
        f'text-anchor="middle" fill="#000">{line}</text>'
        for ly, line in zip(line_ys, label_lines)
    )

    return (
        f'<rect x="{x}" y="{y}" width="{MODULE_W}" height="{MODULE_H}" '
        f'fill="{color}" stroke="#37474F" stroke-width="1"/>'
        f'<text x="{x + MODULE_W // 2}" y="{y + 20}" font-size="14" '
        f'font-weight="bold" text-anchor="middle" fill="#000">'
        f'{circuit.breaker_amps}A{type_a_marker}</text>'
        + label_svg +
        f'<text x="{x + MODULE_W // 2}" y="{y + 92}" font-size="8" '
        f'font-style="italic" text-anchor="middle" fill="#37474F">'
        f'{circuit.cable_section_mm2} mm²</text>'
    )


def render_html_table(tableau: Tableau) -> str:
    """Liste HTML descriptive de tous les circuits."""
    parts: list[str] = [
        '<table style="width:100%; border-collapse:collapse; '
        'font-family:Inter,sans-serif; font-size:13px">',
        '<tr style="background:#37474F; color:white">'
        '<th style="padding:6px; text-align:left">ID</th>'
        '<th style="padding:6px; text-align:left">Type</th>'
        '<th style="padding:6px; text-align:right">Calibre</th>'
        '<th style="padding:6px; text-align:right">Section</th>'
        '<th style="padding:6px; text-align:left">Pièces alimentées</th>'
        '</tr>',
    ]

    row_idx = 0
    type_labels_fr = {
        CircuitType.LIGHTING: "Éclairage",
        CircuitType.SOCKET: "Prises",
        CircuitType.KITCHEN_SPECIAL: "Cuisine spé",
        CircuitType.LAUNDRY: "Buanderie",
        CircuitType.BOILER: "Cumulus (ECS)",
        CircuitType.HEATING: "Chauffage",
        CircuitType.TOWEL_WARMER: "Sèche-serv.",
        CircuitType.KITCHEN_SOCKET: "Prises cuisine",
        CircuitType.VMC: "VMC",
        CircuitType.HEAT_PUMP: "Pompe à chaleur",
        CircuitType.EV_CHARGER: "Borne véhicule",
    }
    for rcd in tableau.rcds:
        for circuit in rcd.circuits:
            bg = "#F5F5F5" if row_idx % 2 == 0 else "white"
            rooms_str = ", ".join(circuit.rooms_served) or "—"
            type_a_marker = " *" if circuit.requires_type_a else ""
            parts.append(
                f'<tr style="background:{bg}">'
                f'<td style="padding:6px">ID {tableau.rcds.index(rcd)+1} '
                f'Type {rcd.rcd_type}</td>'
                f'<td style="padding:6px">{circuit.label}{type_a_marker}</td>'
                f'<td style="padding:6px; text-align:right">'
                f'{circuit.breaker_amps} A</td>'
                f'<td style="padding:6px; text-align:right">'
                f'{circuit.cable_section_mm2} mm²</td>'
                f'<td style="padding:6px">{rooms_str}</td>'
                f'</tr>'
            )
            row_idx += 1

    parts.append('</table>')
    parts.append(
        '<p style="font-size:11px; color:#888; margin-top:4px">'
        '* = Type A obligatoire</p>'
    )
    return "".join(parts)


def export_pdf(tableau: Tableau) -> bytes:
    """Génère un PDF A4 portrait : header + schéma + liste circuits + footer."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, page_h - 20 * mm,
                 f"batIA · Tableau électrique · {tableau.typology}")
    c.setFont("Helvetica", 9)
    from datetime import date
    c.drawString(20 * mm, page_h - 27 * mm,
                 f"Date : {date.today().isoformat()}  ·  "
                 f"Logement : {tableau.typology}  ·  "
                 f"Chauffage : {'oui' if tableau.heating_enabled else 'non'}")

    # Schéma simplifié (rectangles colorés)
    y_cursor = page_h - 45 * mm
    mod_w_mm = 8 * mm
    mod_h_mm = 14 * mm
    rcd_w_mm = 32 * mm
    for rcd_idx, rcd in enumerate(tableau.rcds, start=1):
        # Bloc RCD
        c.setStrokeColor(colors.black)
        c.setFillColor(colors.white)
        c.rect(20 * mm, y_cursor - mod_h_mm, rcd_w_mm, mod_h_mm,
               stroke=1, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 5 * mm,
                            f"ID {rcd_idx}")
        c.setFont("Helvetica", 7)
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 9 * mm,
                            f"{rcd.amps} A · Type {rcd.rcd_type}")
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 12 * mm,
                            f"{rcd.sensitivity_ma} mA")

        # Modules
        for j, circ in enumerate(rcd.circuits):
            x = 20 * mm + rcd_w_mm + j * mod_w_mm
            hex_color = CIRCUIT_COLORS.get(circ.type, "#CCCCCC")
            c.setFillColor(colors.HexColor(hex_color))
            c.setStrokeColor(colors.HexColor("#37474F"))
            c.rect(x, y_cursor - mod_h_mm, mod_w_mm, mod_h_mm,
                   stroke=1, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(x + mod_w_mm / 2, y_cursor - 4 * mm,
                                f"{circ.breaker_amps}A")
            c.setFont("Helvetica", 6)
            short = circ.label[:8]
            c.drawCentredString(x + mod_w_mm / 2, y_cursor - 9 * mm, short)

        y_cursor -= mod_h_mm + 2 * mm

    # Liste circuits (textuelle)
    y_cursor -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y_cursor, "Détail des circuits")
    y_cursor -= 6 * mm
    c.setFont("Helvetica", 8)
    for rcd in tableau.rcds:
        for circ in rcd.circuits:
            line = (
                f"ID {tableau.rcds.index(rcd)+1} Type {rcd.rcd_type} | "
                f"{circ.label} | {circ.breaker_amps} A | "
                f"{circ.cable_section_mm2} mm² | "
                f"{', '.join(circ.rooms_served) or '—'}"
            )
            c.drawString(20 * mm, y_cursor, line[:120])
            y_cursor -= 4 * mm
            if y_cursor < 30 * mm:
                c.showPage()
                y_cursor = page_h - 20 * mm

    # Footer
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(20 * mm, 15 * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. "
                 "Sections câbles indicatives. L'artisan valide la conformité finale.")

    c.save()
    return buf.getvalue()
