"""Énumérations métier facturation. Toutes utilisées comme types de colonnes
SQLAlchemy + valeurs partagées service/UI.

Aligné EN16931 quand applicable (codes BT-*).
"""
from __future__ import annotations

import enum


class FormeJuridique(str, enum.Enum):
    EI = "EI"
    EURL = "EURL"
    SARL = "SARL"
    SAS = "SAS"
    SASU = "SASU"
    SA = "SA"
    AUTRE = "AUTRE"


class TypeClient(str, enum.Enum):
    PARTICULIER = "particulier"
    PROFESSIONNEL = "professionnel"


class DevisStatut(str, enum.Enum):
    BROUILLON = "brouillon"
    ENVOYE = "envoye"
    ACCEPTE = "accepte"
    REFUSE = "refuse"


class FactureType(str, enum.Enum):
    """EN16931 BT-3.

    380 = facture commerciale standard
    386 = acompte (advance payment)
    326 = facture de situation (partial)
    381 = avoir (credit note)
    """
    STANDARD = "380"
    ACOMPTE = "386"
    SITUATION = "326"
    AVOIR = "381"


class FactureStatut(str, enum.Enum):
    BROUILLON = "brouillon"
    EMISE = "emise"
    ENVOYEE = "envoyee"
    PARTIELLEMENT_PAYEE = "partiellement_payee"
    PAYEE = "payee"
    EN_RETARD = "en_retard"
    ANNULEE = "annulee"


class ModePaiement(str, enum.Enum):
    """EN16931 BT-81 (UN/ECE Rec 4461 codes)."""
    VIREMENT = "30"
    CHEQUE = "20"
    CB = "48"
    ESPECES = "10"
    PRELEVEMENT = "58"


class CategorieTVA(str, enum.Enum):
    """EN16931 BT-151."""
    STANDARD = "S"
    EXEMPT = "E"
    ZERO = "Z"
    REVERSE_CHARGE = "AE"
    INTRA_COMMUNITY = "K"
    EXPORT = "G"
    OUT_OF_SCOPE = "O"


class UniteFacturation(str, enum.Enum):
    """EN16931 BT-130 (UN/ECE Rec 20)."""
    UNITE = "C62"
    HEURE = "HUR"
    METRE = "MTR"
    MCARRE = "MTK"
    MCUBE = "MTQ"
    KG = "KGM"
    PIECE = "H87"
    JOUR = "JOU"


class TypeCompteur(str, enum.Enum):
    """Préfixes de numérotation par type de document."""
    DEVIS = "DEV"
    FACTURE = "FAC"
    AVOIR = "AVO"
    AVENANT = "AVE"


class ActionAudit(str, enum.Enum):
    CREATION = "CREATION"
    MODIFICATION = "MODIFICATION"
    EMISSION = "EMISSION"
    ENVOI = "ENVOI"
    PAIEMENT = "PAIEMENT"
    ANNULATION = "ANNULATION"
    ACCEPTATION_DEVIS = "ACCEPTATION_DEVIS"
    REFUS_DEVIS = "REFUS_DEVIS"
    AVENANT_CREE = "AVENANT_CREE"
    AVENANT_ACCEPTE = "AVENANT_ACCEPTE"
