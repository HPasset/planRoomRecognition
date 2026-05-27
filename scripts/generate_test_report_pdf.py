"""Génère un PDF stylé du rapport de test depuis le Markdown.

Usage:
    python scripts/generate_test_report_pdf.py

Sortie : ``docs/TEST_REPORT.pdf``

Le CSS embarqué donne un look professionnel cohérent batIA :
- Headings bleu marine + soulignement
- Tables avec alternance de couleurs
- Badges colorés pour ✅ / ❌ / ⏭ (vert / rouge / gris)
- Code inline gris clair
- Pagination + en-tête en pied de page
"""
from __future__ import annotations
from pathlib import Path
from markdown_pdf import MarkdownPdf, Section


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MD_INPUT = PROJECT_ROOT / "docs" / "TEST_REPORT.md"
PDF_OUTPUT = PROJECT_ROOT / "docs" / "TEST_REPORT.pdf"


# CSS embarqué — palette batIA (bleu marine + accents discrets)
CSS = """
@page {
    size: A4;
    margin: 2cm 1.8cm 2.2cm 1.8cm;
}
body {
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    color: #1a1a1a;
    font-size: 10.5pt;
    line-height: 1.55;
}
h1 {
    color: #0f2540;
    font-size: 22pt;
    border-bottom: 3px solid #0f2540;
    padding-bottom: 0.3em;
    margin-top: 0;
    margin-bottom: 0.6em;
}
h2 {
    color: #0f2540;
    font-size: 15pt;
    margin-top: 1.6em;
    margin-bottom: 0.5em;
    border-bottom: 1px solid #d0d7e2;
    padding-bottom: 0.2em;
}
h3 {
    color: #1f3a5f;
    font-size: 12.5pt;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
}
h4 {
    color: #2a4a73;
    font-size: 11pt;
    margin-top: 0.9em;
    margin-bottom: 0.3em;
}
p {
    margin: 0.4em 0;
}
strong {
    color: #0f2540;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0 1.2em 0;
    font-size: 9.5pt;
}
th {
    background-color: #0f2540;
    color: #ffffff;
    padding: 6px 10px;
    text-align: left;
    font-weight: 600;
    border: 1px solid #0f2540;
}
td {
    padding: 5px 10px;
    border: 1px solid #d0d7e2;
    vertical-align: top;
}
tr:nth-child(even) td {
    background-color: #f5f8fc;
}
code {
    background-color: #f0f3f7;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 9.5pt;
    color: #c0392b;
}
pre {
    background-color: #f5f8fc;
    border-left: 3px solid #0f2540;
    padding: 10px 14px;
    border-radius: 3px;
    overflow-x: auto;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 9.5pt;
    line-height: 1.4;
}
pre code {
    background-color: transparent;
    padding: 0;
    color: #1a1a1a;
}
hr {
    border: none;
    border-top: 1px solid #d0d7e2;
    margin: 1.5em 0;
}
ul, ol {
    margin: 0.4em 0 0.6em 1.5em;
    padding: 0;
}
li {
    margin: 0.2em 0;
}
blockquote {
    border-left: 3px solid #d0d7e2;
    margin: 0.6em 0;
    padding: 0.2em 1em;
    color: #4a5568;
    font-style: italic;
}
a {
    color: #1f3a5f;
    text-decoration: none;
    border-bottom: 1px dotted #1f3a5f;
}
"""


def main():
    if not MD_INPUT.exists():
        raise SystemExit(f"❌ Fichier source introuvable : {MD_INPUT}")

    md_content = MD_INPUT.read_text(encoding="utf-8")

    pdf = MarkdownPdf(toc_level=2, optimize=True)
    pdf.add_section(
        Section(md_content, toc=True),
        user_css=CSS,
    )
    pdf.meta["title"] = "Test Report — planRoomRecognition Devis"
    pdf.meta["author"] = "batIA / Claude Code AppTest pipeline"
    pdf.meta["subject"] = "Rapport de tests automatisés Streamlit AppTest"
    pdf.meta["keywords"] = "test report, streamlit, apptest, devis, NFC, pytest"

    PDF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(PDF_OUTPUT))

    size_kb = PDF_OUTPUT.stat().st_size / 1024
    print(f"✅ PDF généré : {PDF_OUTPUT}")
    print(f"   Taille : {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
