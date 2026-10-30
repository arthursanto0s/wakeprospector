"""Responsible person and contact identification service for Wake Prospector (Phase 3).

Enforces strict rules on:
- Person <-> Company relationship verification (preventing false owners - T02)
- Person <-> Phone separate association (preventing phone ambiguity - T03)
- Conflict detection between divergent sources (T06)
- Confidence assignment and uncertainty logging
"""

import re
from typing import List, Optional, Tuple

from src.config import (
    ConfidenceLevel,
    ContactType,
    PipelineStatus,
    SourceType,
)
from src.database import DatabaseManager
from src.deduplication import normalize_phone
from src.logger import get_logger, log_event
from src.models import (
    Contact,
    Lead,
    Source,
)

logger = get_logger()

# Patterns that indicate weak/non-probative owner attribution
WEAK_EVIDENCE_PATTERNS = re.compile(
    r"\b(mesmo\s+sobrenome|sobrenome\s+coincide|aparece\s+em\s+foto|foto|segue\s+a\s+empresa|perfil\s+semelhante|primeiro\s+no\s+google)\b",
    re.IGNORECASE,
)


class ResponsibleService:
    """Manages responsible identification, contact verification, and conflict detection."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def add_responsible(
        self,
        lead_id: str,
        name: str,
        role: str,
        source: Source,
        relationship_proof: str,
        confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    ) -> Tuple[Lead, Contact, bool]:
        """Adds or updates an identified responsible person on a lead.

        Enforces critical rules:
        1. T02 (False Owner): If proof only cites surname, photo, or weak indications,
           confidence is degraded to LOW/UNKNOWN and uncertainty is explicitly logged.
        2. T06 (Conflicting Owner): If another responsible person is already recorded with
           a different name, records a CONFLICT uncertainty and degrades confidence.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        clean_name = name.strip()
        clean_role = role.strip()
        clean_proof = relationship_proof.strip()

        # Check for weak evidence (T02)
        is_weak_evidence = bool(WEAK_EVIDENCE_PATTERNS.search(clean_proof))
        if is_weak_evidence:
            confidence = ConfidenceLevel.LOW
            lead.opportunity.uncertainties.append(
                f"Atenção (T02): Associação de '{clean_name}' como '{clean_role}' baseia-se em indício fraco: '{clean_proof}'. Vínculo não confirmado."
            )

        # Check for conflicting owner/administrator (T06)
        has_conflict = False
        for existing_contact in lead.contacts:
            if (
                existing_contact.name
                and existing_contact.name.lower() != clean_name.lower()
            ):
                # Both claim leadership/ownership roles
                conflict_msg = (
                    f"CONFLITO DE RESPONSÁVEL (T06): Fonte '{source.title}' aponta '{clean_name}' ({clean_role}), "
                    f"enquanto registro anterior aponta '{existing_contact.name}' ({existing_contact.role}). Fontes divergentes."
                )
                lead.opportunity.uncertainties.append(conflict_msg)
                confidence = ConfidenceLevel.LOW
                existing_contact.confidence = ConfidenceLevel.LOW
                has_conflict = True

        # Append source
        lead.sources.append(source)

        # Create contact entry
        contact = Contact(
            name=clean_name,
            role=clean_role,
            phone="",
            type=ContactType.BUSINESS,
            confidence=confidence,
            evidence_ids=[source.id],
        )
        lead.contacts.append(contact)

        # Save lead state
        lead = self.db.save_lead(lead)

        # Advance pipeline status if eligible: NO_WEBSITE or VERIFIED -> RESPONSIBLE_FOUND
        if (
            lead.pipeline_status
            in (
                PipelineStatus.NEW,
                PipelineStatus.RESEARCHING,
                PipelineStatus.VERIFIED,
                PipelineStatus.NO_WEBSITE,
            )
            and not is_weak_evidence
        ):
            # Advance deterministically through pipeline sequence
            if lead.pipeline_status == PipelineStatus.NEW:
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.RESEARCHING, lead=lead
                )
            if lead.pipeline_status == PipelineStatus.RESEARCHING:
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.VERIFIED, lead=lead
                )
            if lead.pipeline_status == PipelineStatus.VERIFIED:
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.NO_WEBSITE, lead=lead
                )
            if lead.pipeline_status == PipelineStatus.NO_WEBSITE:
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.RESPONSIBLE_FOUND, lead=lead
                )

        log_entry = log_event(
            event_type="RESPONSIBLE_IDENTIFIED",
            lead_id=lead.id,
            details={
                "name": clean_name,
                "role": clean_role,
                "confidence": confidence.value,
                "is_weak_evidence": is_weak_evidence,
                "has_conflict": has_conflict,
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead, contact, has_conflict

    def associate_phone(
        self,
        lead_id: str,
        contact_id: str,
        phone: str,
        source: Optional[Source] = None,
        is_person_associated: bool = False,
        proof: str = "",
    ) -> Tuple[Lead, Contact]:
        """Associates a phone number to a specific contact on a lead.

        Enforces critical rule T03 (Phone Ambiguity):
        - If is_person_associated is False:
          The phone was found on company channels without proof that it belongs directly to the person.
          Set type = ContactType.BUSINESS.
          Add uncertainty note explaining that the personal link is not verified.
        - If is_person_associated is True:
          Direct public link confirmed (e.g. WhatsApp profissional do responsável).
          Set type = ContactType.PERSONAL_PROFESSIONAL.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        contact = None
        for c in lead.contacts:
            if c.id == contact_id or (not contact_id and c.name):
                contact = c
                break

        if not contact:
            # If no specific contact matched, create a company-level contact
            contact = Contact(
                name="",
                role="Comercial da Empresa",
                type=ContactType.BUSINESS,
            )
            lead.contacts.append(contact)

        norm = normalize_phone(phone)
        contact.phone = phone
        if source:
            lead.sources.append(source)
            if source.id not in contact.evidence_ids:
                contact.evidence_ids.append(source.id)

        if is_person_associated:
            contact.type = ContactType.PERSONAL_PROFESSIONAL
            if contact.confidence in (ConfidenceLevel.UNKNOWN, ConfidenceLevel.LOW):
                contact.confidence = ConfidenceLevel.MEDIUM
        else:
            # T03: company phone, cannot assume personal owner phone
            contact.type = ContactType.BUSINESS
            lead.opportunity.uncertainties.append(
                f"Associação de Telefone (T03): O número {phone} pertence aos canais da empresa. Vínculo particular direto com '{contact.name or 'responsável'}' não foi confirmado."
            )

        # Save lead state
        lead = self.db.save_lead(lead)

        # Advance pipeline status if eligible: RESPONSIBLE_FOUND -> CONTACT_FOUND
        if lead.pipeline_status == PipelineStatus.RESPONSIBLE_FOUND:
            lead = self.db.update_lead_status(
                lead.id, PipelineStatus.CONTACT_FOUND, lead=lead
            )

        log_entry = log_event(
            event_type="CONTACT_PHONE_ASSOCIATED",
            lead_id=lead.id,
            details={
                "contact_name": contact.name,
                "phone": phone,
                "normalized": norm,
                "type": contact.type.value,
                "is_person_associated": is_person_associated,
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead, contact

    def select_recommended_contact(self, lead_id: str) -> Tuple[Lead, Optional[Contact]]:
        """Selects the best contact for outreach based on the priority hierarchy:

        1. Responsible person with verified phone and high confidence
        2. Responsible person with phone
        3. Responsible person without phone
        4. Generic company contact with phone
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        if not lead.contacts:
            return lead, None

        def contact_score(c: Contact) -> int:
            score = 0
            if c.name:
                score += 50
            if c.phone:
                score += 30
            if c.type == ContactType.PERSONAL_PROFESSIONAL:
                score += 20
            if c.confidence == ConfidenceLevel.HIGH:
                score += 15
            elif c.confidence == ConfidenceLevel.MEDIUM:
                score += 10
            return score

        best_contact = max(lead.contacts, key=contact_score)
        lead.outreach.recommended_contact_id = best_contact.id

        lead = self.db.save_lead(lead)
        log_entry = log_event(
            event_type="RECOMMENDED_CONTACT_SELECTED",
            lead_id=lead.id,
            details={
                "recommended_contact_id": best_contact.id,
                "name": best_contact.name,
                "role": best_contact.role,
                "phone": best_contact.phone,
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead, best_contact
