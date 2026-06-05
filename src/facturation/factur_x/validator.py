"""Validation structurelle du XML Factur-X.

Phase A : checks BT-* critiques. Phase C : validation XSD EN16931 officielle.
"""
from __future__ import annotations

from lxml import etree


class FacturXValidationError(ValueError):
    """Levée quand le XML CII n'est pas conforme EN16931 minimal."""


_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


def validate_minimal(xml_bytes: bytes) -> None:
    """Vérifie présence des champs BT-* critiques.

    Lève FacturXValidationError si quelque chose manque.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        raise FacturXValidationError(f"XML malformé : {e}") from e

    required = {
        "BT-1 invoice number":
            "//rsm:ExchangedDocument/ram:ID/text()",
        "BT-3 type code":
            "//rsm:ExchangedDocument/ram:TypeCode/text()",
        "BT-2 issue date":
            "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString/text()",
        "BT-27 seller name":
            "//ram:SellerTradeParty/ram:Name/text()",
        "BT-29 seller SIRET":
            "//ram:SellerTradeParty/ram:SpecifiedLegalOrganization/ram:ID/text()",
        "BT-44 buyer name":
            "//ram:BuyerTradeParty/ram:Name/text()",
        "BT-106 line total":
            "//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:LineTotalAmount/text()",
        "BT-110 total tax":
            "//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:TaxTotalAmount/text()",
        "BT-112 grand total":
            "//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:GrandTotalAmount/text()",
    }

    missing = []
    for name, xpath in required.items():
        result = root.xpath(xpath, namespaces=_NS)
        if not result or not str(result[0]).strip():
            missing.append(name)

    if missing:
        raise FacturXValidationError(
            f"Champs EN16931 obligatoires manquants : {missing}"
        )
