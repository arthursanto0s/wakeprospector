"""Research and verification service for Wake Prospector (Phase 2).

Provides deterministic support for candidate ingestion, deduplication check,
entity identity corroboration, and website status verification without
replacing the agent's contextual investigation.
"""

from typing import List, Optional, Tuple

from src.config import (
    ConfidenceLevel,
    ContactType,
    PipelineStatus,
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.deduplication import (
    check_lead_duplicate,
    extract_domain,
    is_generic_domain,
)
from src.logger import get_logger, log_event
from src.models import (
    AuditLogEntry,
    Business,
    Contact,
    Lead,
    Source,
)

logger = get_logger()


class ResearchService:
    """Orchestrates deterministic operations for discovery, entity verification,

    and website status tracking.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def ingest_candidate(
        self,
        name: str,
        city: str,
        category: str = "",
        neighborhood: str = "",
        address: str = "",
        initial_source: Optional[Source] = None,
        phone: Optional[str] = None,
    ) -> Tuple[Lead, bool, Optional[str]]:
        """Ingests a newly discovered candidate entity.

        Checks against existing leads to avoid creating duplicates.
        - If high-confidence duplicate found: links source to existing lead and returns (existing_lead, False, reason).
        - If unique: creates new Lead, saves to SQLite, and returns (new_lead, True, None).
        """
        contacts = []
        if phone:
            contacts.append(
                Contact(
                    name="",
                    role="Empresa",
                    phone=phone,
                    type=ContactType.BUSINESS,
                    confidence=ConfidenceLevel.MEDIUM,
                    evidence_ids=[initial_source.id] if initial_source else [],
                )
            )

        candidate = Lead(
            business=Business(
                name=name,
                category=category,
                city=city,
                neighborhood=neighborhood,
                address=address,
                website_status=WebsiteStatus.UNKNOWN,
            ),
            contacts=contacts,
            pipeline_status=PipelineStatus.NEW,
        )

        if initial_source:
            candidate.sources.append(initial_source)

        existing_leads = self.db.list_leads()
        dup_result = check_lead_duplicate(candidate, existing_leads)

        if dup_result.is_duplicate and dup_result.confidence == ConfidenceLevel.HIGH:
            # Re-use existing lead, append source if new
            existing_lead = self.db.get_lead(dup_result.matched_lead_id)
            if existing_lead and initial_source:
                # Check if source URL already exists
                existing_urls = {s.url for s in existing_lead.sources if s.url}
                if initial_source.url not in existing_urls:
                    existing_lead.sources.append(initial_source)
                    self.db.save_lead(existing_lead)
                    log_entry = log_event(
                        event_type="DUPLICATE_SOURCE_MERGED",
                        lead_id=existing_lead.id,
                        details={
                            "new_source": initial_source.title,
                            "url": initial_source.url,
                            "reason": dup_result.reason,
                        },
                    )
                    self.db.insert_audit_log(log_entry)
            return existing_lead or candidate, False, dup_result.reason

        # If duplicate with medium confidence (similarity in same city), register note
        if dup_result.is_duplicate and dup_result.confidence == ConfidenceLevel.MEDIUM:
            candidate.opportunity.uncertainties.append(
                f"Atenção de duplicidade: {dup_result.reason}"
            )

        saved = self.db.save_lead(candidate)
        log_entry = log_event(
            event_type="CANDIDATE_INGESTED",
            lead_id=saved.id,
            details={
                "business_name": name,
                "city": city,
                "category": category,
            },
        )
        self.db.insert_audit_log(log_entry)
        return saved, True, None

    def verify_company_identity(
        self,
        lead_id: str,
        source: Source,
        confirmed_address: Optional[str] = None,
        confirmed_neighborhood: Optional[str] = None,
        confirmed_category: Optional[str] = None,
    ) -> Lead:
        """Adds corroborating source evidence for entity identity and advances status to VERIFIED."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        lead.sources.append(source)
        if confirmed_address:
            lead.business.address = confirmed_address
        if confirmed_neighborhood:
            lead.business.neighborhood = confirmed_neighborhood
        if confirmed_category:
            lead.business.category = confirmed_category

        # Save in-memory fields first
        lead = self.db.save_lead(lead)

        # Transition status: NEW/RESEARCHING -> VERIFIED
        if lead.pipeline_status in (PipelineStatus.NEW, PipelineStatus.RESEARCHING):
            if lead.pipeline_status == PipelineStatus.NEW:
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.RESEARCHING, lead=lead
                )
            lead = self.db.update_lead_status(
                lead.id, PipelineStatus.VERIFIED, lead=lead
            )

        log_entry = log_event(
            event_type="ENTITY_VERIFIED",
            lead_id=lead.id,
            details={
                "source_title": source.title,
                "source_type": str(source.source_type),
                "total_sources": len(lead.sources),
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead

    def record_website_verification(
        self,
        lead_id: str,
        website_url: str = "",
        website_status: WebsiteStatus = WebsiteStatus.UNKNOWN,
        evidence_source: Optional[Source] = None,
        notes: Optional[str] = None,
    ) -> Lead:
        """Records website verification results.

        Enforces critical rules from docs/PROJECT_SPEC.md & docs/TEST_PLAN.md:
        1. Social profiles / directory links (Instagram, Facebook, etc.) are NOT own websites.
        2. If official domain confirmed (WEBSITE_FOUND): marks website_status=WEBSITE_FOUND,
           and marks lead as DISCARDED with reason 'Possui site próprio (fora do escopo V1)'.
        3. If NO_WEBSITE_CONFIRMED or NO_WEBSITE_FOUND: updates website_status and transitions lead to NO_WEBSITE.
        4. If UNCERTAIN: records uncertainty in opportunity notes.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        cleaned_url = website_url.strip()
        domain = extract_domain(cleaned_url)

        # Rule check: social media / directory profiles are not own websites
        if cleaned_url and is_generic_domain(domain):
            if "instagram" in domain:
                lead.digital_presence.instagram = cleaned_url
            elif "facebook" in domain or "fb.com" in domain:
                lead.digital_presence.facebook = cleaned_url
            elif "google" in domain or "maps" in domain:
                lead.digital_presence.google_maps = cleaned_url
            else:
                lead.digital_presence.other.append(cleaned_url)

            # Do not consider this an own website
            cleaned_url = ""
            if website_status == WebsiteStatus.WEBSITE_FOUND:
                website_status = WebsiteStatus.NO_WEBSITE_FOUND
                notes = (
                    (notes or "")
                    + " [URL informada é perfil de rede social/diretório, não site próprio]."
                ).strip()

        if evidence_source:
            lead.sources.append(evidence_source)

        if notes:
            lead.opportunity.uncertainties.append(f"Nota de checagem de site: {notes}")

        lead.business.website = cleaned_url
        lead.business.website_status = website_status

        # Save lead state with updated website fields first
        lead = self.db.save_lead(lead)

        # Pipeline state adjustments
        if website_status == WebsiteStatus.WEBSITE_FOUND:
            # Excluded from V1 target queue as per Decision D002 & Test T04
            discard_reason = f"Empresa possui site próprio confirmado: {cleaned_url} (excluída do foco V1)"
            lead = self.db.update_lead_status(
                lead.id,
                PipelineStatus.DISCARDED,
                reason=discard_reason,
                lead=lead,
            )
        elif website_status in (
            WebsiteStatus.NO_WEBSITE_CONFIRMED,
            WebsiteStatus.NO_WEBSITE_FOUND,
        ):
            if lead.pipeline_status in (
                PipelineStatus.NEW,
                PipelineStatus.RESEARCHING,
                PipelineStatus.VERIFIED,
            ):
                # Ensure it passes through RESEARCHING and VERIFIED if coming from NEW
                if lead.pipeline_status == PipelineStatus.NEW:
                    lead = self.db.update_lead_status(
                        lead.id, PipelineStatus.RESEARCHING, lead=lead
                    )
                if lead.pipeline_status == PipelineStatus.RESEARCHING:
                    lead = self.db.update_lead_status(
                        lead.id, PipelineStatus.VERIFIED, lead=lead
                    )
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.NO_WEBSITE, lead=lead
                )

        log_entry = log_event(
            event_type="WEBSITE_VERIFICATION_RECORDED",
            lead_id=lead.id,
            details={
                "website_url": cleaned_url,
                "website_status": str(website_status.value),
                "notes": notes or "",
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead

    def log_research_query(
        self, query: str, purpose: str, lead_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Persists a search query to the audit log."""
        entry = log_event(
            event_type="RESEARCH_QUERY",
            lead_id=lead_id,
            details={"query": query, "purpose": purpose},
        )
        self.db.insert_audit_log(entry)
        return entry
