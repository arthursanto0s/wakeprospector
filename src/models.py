"""Deterministic data models for Wake Prospector based on docs/LEAD_DATA_MODEL.md."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any, Optional

from src.config import (
    PipelineStatus,
    WebsiteStatus,
    ConfidenceLevel,
    OpportunityClass,
    SourceType,
    ContactType,
    ResponseIntent,
)


def utc_now_iso() -> str:
    """Returns the current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def generate_lead_id() -> str:
    """Generates an ID in the format LEAD-YYYY-XXXXXX."""
    year = datetime.now(timezone.utc).strftime("%Y")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"LEAD-{year}-{unique_suffix}"


def generate_source_id() -> str:
    """Generates an ID in the format SRC-XXXXXX."""
    return f"SRC-{uuid.uuid4().hex[:6].upper()}"


def generate_contact_id() -> str:
    """Generates an ID in the format CONT-XXXXXX."""
    return f"CONT-{uuid.uuid4().hex[:6].upper()}"


def generate_log_id() -> str:
    """Generates an ID in the format LOG-XXXXXX."""
    return f"LOG-{uuid.uuid4().hex[:6].upper()}"


def generate_conv_id() -> str:
    """Generates an ID in the format CONV-XXXXXX."""
    return f"CONV-{uuid.uuid4().hex[:6].upper()}"


@dataclass
class Source:
    id: str = field(default_factory=generate_source_id)
    url: str = ""
    title: str = ""
    source_type: SourceType = SourceType.E1
    accessed_at: str = field(default_factory=utc_now_iso)
    supports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "source_type": (
                self.source_type.value
                if isinstance(self.source_type, SourceType)
                else str(self.source_type)
            ),
            "accessed_at": self.accessed_at,
            "supports": list(self.supports),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Source":
        st = data.get("source_type", SourceType.E1.value)
        try:
            source_type = SourceType(st)
        except ValueError:
            source_type = SourceType.E4
        return cls(
            id=data.get("id") or generate_source_id(),
            url=data.get("url", ""),
            title=data.get("title", ""),
            source_type=source_type,
            accessed_at=data.get("accessed_at") or utc_now_iso(),
            supports=list(data.get("supports", [])),
        )


@dataclass
class Contact:
    id: str = field(default_factory=generate_contact_id)
    name: str = ""
    role: str = ""
    phone: str = ""
    type: ContactType = ContactType.BUSINESS
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "phone": self.phone,
            "type": (
                self.type.value
                if isinstance(self.type, ContactType)
                else str(self.type)
            ),
            "confidence": (
                self.confidence.value
                if isinstance(self.confidence, ConfidenceLevel)
                else str(self.confidence)
            ),
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contact":
        ct = data.get("type", ContactType.BUSINESS.value)
        try:
            contact_type = ContactType(ct)
        except ValueError:
            contact_type = ContactType.UNCERTAIN

        cf = data.get("confidence", ConfidenceLevel.UNKNOWN.value)
        try:
            confidence = ConfidenceLevel(cf)
        except ValueError:
            confidence = ConfidenceLevel.UNKNOWN

        return cls(
            id=data.get("id") or generate_contact_id(),
            name=data.get("name", ""),
            role=data.get("role", ""),
            phone=data.get("phone", ""),
            type=contact_type,
            confidence=confidence,
            evidence_ids=list(data.get("evidence_ids", [])),
        )


@dataclass
class Business:
    name: str = ""
    category: str = ""
    city: str = ""
    neighborhood: str = ""
    address: str = ""
    website: str = ""
    website_status: WebsiteStatus = WebsiteStatus.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "city": self.city,
            "neighborhood": self.neighborhood,
            "address": self.address,
            "website": self.website,
            "website_status": (
                self.website_status.value
                if isinstance(self.website_status, WebsiteStatus)
                else str(self.website_status)
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Business":
        ws = data.get("website_status", WebsiteStatus.UNKNOWN.value)
        try:
            website_status = WebsiteStatus(ws)
        except ValueError:
            website_status = WebsiteStatus.UNKNOWN

        return cls(
            name=data.get("name", ""),
            category=data.get("category", ""),
            city=data.get("city", ""),
            neighborhood=data.get("neighborhood", ""),
            address=data.get("address", ""),
            website=data.get("website", ""),
            website_status=website_status,
        )


@dataclass
class DigitalPresence:
    instagram: str = ""
    facebook: str = ""
    google_maps: str = ""
    other: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instagram": self.instagram,
            "facebook": self.facebook,
            "google_maps": self.google_maps,
            "other": list(self.other),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DigitalPresence":
        return cls(
            instagram=data.get("instagram", ""),
            facebook=data.get("facebook", ""),
            google_maps=data.get("google_maps", ""),
            other=list(data.get("other", [])),
        )


@dataclass
class Opportunity:
    classification: OpportunityClass = OpportunityClass.UNCERTAIN
    evidence: List[str] = field(default_factory=list)
    hypothesis: str = ""
    uncertainties: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": (
                self.classification.value
                if isinstance(self.classification, OpportunityClass)
                else str(self.classification)
            ),
            "evidence": list(self.evidence),
            "hypothesis": self.hypothesis,
            "uncertainties": list(self.uncertainties),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Opportunity":
        op = data.get("classification", OpportunityClass.UNCERTAIN.value)
        try:
            classification = OpportunityClass(op)
        except ValueError:
            classification = OpportunityClass.UNCERTAIN

        return cls(
            classification=classification,
            evidence=list(data.get("evidence", [])),
            hypothesis=data.get("hypothesis", ""),
            uncertainties=list(data.get("uncertainties", [])),
        )


@dataclass
class Outreach:
    recommended_contact_id: str = ""
    opening_message: str = ""
    human_review: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommended_contact_id": self.recommended_contact_id,
            "opening_message": self.opening_message,
            "human_review": self.human_review,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Outreach":
        return cls(
            recommended_contact_id=data.get("recommended_contact_id", ""),
            opening_message=data.get("opening_message", ""),
            human_review=bool(data.get("human_review", True)),
        )


@dataclass
class Lead:
    id: str = field(default_factory=generate_lead_id)
    business: Business = field(default_factory=Business)
    contacts: List[Contact] = field(default_factory=list)
    digital_presence: DigitalPresence = field(default_factory=DigitalPresence)
    opportunity: Opportunity = field(default_factory=Opportunity)
    outreach: Outreach = field(default_factory=Outreach)
    sources: List[Source] = field(default_factory=list)
    pipeline_status: PipelineStatus = PipelineStatus.NEW
    discard_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "business": self.business.to_dict(),
            "contacts": [c.to_dict() for c in self.contacts],
            "digital_presence": self.digital_presence.to_dict(),
            "opportunity": self.opportunity.to_dict(),
            "outreach": self.outreach.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "pipeline_status": (
                self.pipeline_status.value
                if isinstance(self.pipeline_status, PipelineStatus)
                else str(self.pipeline_status)
            ),
            "discard_reason": self.discard_reason,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lead":
        ps = data.get("pipeline_status", PipelineStatus.NEW.value)
        try:
            pipeline_status = PipelineStatus(ps)
        except ValueError:
            pipeline_status = PipelineStatus.UNCERTAIN

        return cls(
            id=data.get("id") or generate_lead_id(),
            business=Business.from_dict(data.get("business", {})),
            contacts=[Contact.from_dict(c) for c in data.get("contacts", [])],
            digital_presence=DigitalPresence.from_dict(
                data.get("digital_presence", {})
            ),
            opportunity=Opportunity.from_dict(data.get("opportunity", {})),
            outreach=Outreach.from_dict(data.get("outreach", {})),
            sources=[Source.from_dict(s) for s in data.get("sources", [])],
            pipeline_status=pipeline_status,
            discard_reason=data.get("discard_reason"),
            metadata=dict(data.get("metadata", {})),
            discovered_at=data.get("discovered_at") or utc_now_iso(),
            updated_at=data.get("updated_at") or utc_now_iso(),
        )


@dataclass
class Conversation:
    id: str = field(default_factory=generate_conv_id)
    lead_id: str = ""
    timestamp: str = field(default_factory=utc_now_iso)
    direction: str = "INBOUND"  # INBOUND or OUTBOUND
    text: str = ""
    intent: ResponseIntent = ResponseIntent.UNCERTAIN
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "text": self.text,
            "intent": (
                self.intent.value
                if isinstance(self.intent, ResponseIntent)
                else str(self.intent)
            ),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        it = data.get("intent", ResponseIntent.UNCERTAIN.value)
        try:
            intent = ResponseIntent(it)
        except ValueError:
            intent = ResponseIntent.UNCERTAIN

        return cls(
            id=data.get("id") or generate_conv_id(),
            lead_id=data.get("lead_id", ""),
            timestamp=data.get("timestamp") or utc_now_iso(),
            direction=data.get("direction", "INBOUND"),
            text=data.get("text", ""),
            intent=intent,
            notes=data.get("notes", ""),
        )


@dataclass
class AuditLogEntry:
    id: str = field(default_factory=generate_log_id)
    lead_id: Optional[str] = None
    event_type: str = ""
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "event_type": self.event_type,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLogEntry":
        return cls(
            id=data.get("id") or generate_log_id(),
            lead_id=data.get("lead_id"),
            event_type=data.get("event_type", ""),
            from_status=data.get("from_status"),
            to_status=data.get("to_status"),
            details=dict(data.get("details", {})),
            timestamp=data.get("timestamp") or utc_now_iso(),
        )
