"""Interface abstraite `PAAdapter` — contrat batIA ↔ Plateforme Agréée tierce.

batIA = passerelle. Cette interface définit ce que tout PA partenaire
(Pennylane, Sage, Cegid, Indy, etc.) doit exposer pour qu'on puisse y
brancher une facture émise.

Implémentation concrète : Phase D, après choix du PA cible. Phase A ne
livre que cette interface + un mock pour valider l'architecture.

Cycle de vie côté PA (BT-* lifecycle EN16931) :
- submitted    : envoyé au PA, attente acheminement
- received     : PA confirme réception
- routed       : transmis au destinataire via PPF
- read         : destinataire a accédé
- accepted     : destinataire a validé (ou délai expiré sans contestation)
- rejected     : destinataire a refusé
- paid         : paiement enregistré côté PA / banque
- disputed     : litige ouvert
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PALifecycleStatus(str, Enum):
    SUBMITTED = "submitted"
    RECEIVED = "received"
    ROUTED = "routed"
    READ = "read"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PASubmissionResult:
    """Résultat d'un submit_invoice."""
    pa_submission_id: str
    submitted_at: datetime
    status: PALifecycleStatus
    raw_response: dict


@dataclass(frozen=True)
class PAStatusReport:
    """Snapshot des événements lifecycle d'une facture chez le PA."""
    pa_submission_id: str
    current_status: PALifecycleStatus
    last_event_at: datetime
    events: list[dict]


class PAAdapter(ABC):
    """Contrat batIA ↔ PA. Toute implémentation concrète (Phase D) hérite."""

    @abstractmethod
    def submit_invoice(self, *, facturx_pdf: bytes, facture_numero: str,
                       artisan_id: str, client_data: dict) -> PASubmissionResult:
        """Envoie un PDF/A-3 Factur-X au PA pour transmission au PPF.

        - facturx_pdf : le PDF/A-3 avec XML EN16931 embarqué
        - facture_numero : référence batIA (logging et reconciliation)
        - artisan_id : identité émetteur batIA
        - client_data : métadonnées destinataire (le PA peut router au PPF)
        """
        ...

    @abstractmethod
    def get_status(self, pa_submission_id: str) -> PAStatusReport:
        """Récupère le lifecycle courant d'une facture déjà soumise."""
        ...

    @abstractmethod
    def cancel(self, pa_submission_id: str, motif: str) -> None:
        """Annule une facture chez le PA si possible (avant routage PPF)."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Vérifie que l'API du PA est joignable."""
        ...
