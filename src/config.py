"""Configuration, canonical enums, and pipeline transition rules for Wake Prospector."""

from enum import Enum
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "wake_prospector.db"
LOGS_DIR = DATA_DIR / "logs"
LEADS_DIR = DATA_DIR / "leads"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
RESEARCH_DIR = DATA_DIR / "research"
LOG_FILE_PATH = LOGS_DIR / "wake_prospector.log"

# Ensure directories exist
for directory in (DATA_DIR, LOGS_DIR, LEADS_DIR, CONVERSATIONS_DIR, RESEARCH_DIR):
    directory.mkdir(parents=True, exist_ok=True)


class PipelineStatus(str, Enum):
    """Pipeline statuses defined in docs/PROJECT_SPEC.md and docs/LEAD_PIPELINE.md."""
    NEW = "NEW"
    RESEARCHING = "RESEARCHING"
    VERIFIED = "VERIFIED"
    NO_WEBSITE = "NO_WEBSITE"
    RESPONSIBLE_FOUND = "RESPONSIBLE_FOUND"
    CONTACT_FOUND = "CONTACT_FOUND"
    QUALIFIED = "QUALIFIED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    CONTACTED = "CONTACTED"
    WAITING_REPLY = "WAITING_REPLY"
    RESPONDED = "RESPONDED"
    INTERESTED_HANDOFF = "INTERESTED_HANDOFF"
    NOT_INTERESTED = "NOT_INTERESTED"
    NOT_RESPONSIBLE = "NOT_RESPONSIBLE"
    DISCARDED = "DISCARDED"
    UNCERTAIN = "UNCERTAIN"


class WebsiteStatus(str, Enum):
    """Website verification statuses."""
    UNKNOWN = "UNKNOWN"
    WEBSITE_FOUND = "WEBSITE_FOUND"
    NO_WEBSITE_FOUND = "NO_WEBSITE_FOUND"
    NO_WEBSITE_CONFIRMED = "NO_WEBSITE_CONFIRMED"
    UNCERTAIN = "UNCERTAIN"


class ConfidenceLevel(str, Enum):
    """Evidence confidence levels defined in docs/EVIDENCE_AND_CONFIDENCE.md."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class OpportunityClass(str, Enum):
    """Opportunity classification without false precision."""
    STRONG = "STRONG"
    POSSIBLE = "POSSIBLE"
    UNCERTAIN = "UNCERTAIN"
    LOW_PRIORITY = "LOW_PRIORITY"


class SourceType(str, Enum):
    """Source classification levels."""
    E1 = "E1"  # Official / primary (company, official registries, direct posts)
    E2 = "E2"  # Reliable professional source (directories, news, professional profiles)
    E3 = "E3"  # Secondary source (aggregators, replicated listings)
    E4 = "E4"  # Clue / partial indication (mentions without direct proof)


class ContactType(str, Enum):
    """Contact type classification."""
    BUSINESS = "BUSINESS"
    PERSONAL_PROFESSIONAL = "PERSONAL_PROFESSIONAL"
    UNCERTAIN = "UNCERTAIN"


class ResponseIntent(str, Enum):
    """Intent classification for incoming responses."""
    RESPONSIBLE_CONFIRMED = "RESPONSIBLE_CONFIRMED"
    NOT_RESPONSIBLE = "NOT_RESPONSIBLE"
    ASKING_CONTEXT = "ASKING_CONTEXT"
    INTERESTED = "INTERESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    MEETING_REQUEST = "MEETING_REQUEST"
    UNCERTAIN = "UNCERTAIN"


# Allowed state transitions for pipeline integrity
ALLOWED_PIPELINE_TRANSITIONS = {
    PipelineStatus.NEW: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.RESEARCHING: {
        PipelineStatus.VERIFIED,
        PipelineStatus.NO_WEBSITE,
        PipelineStatus.RESPONSIBLE_FOUND,
        PipelineStatus.CONTACT_FOUND,
        PipelineStatus.QUALIFIED,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.VERIFIED: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.NO_WEBSITE,
        PipelineStatus.RESPONSIBLE_FOUND,
        PipelineStatus.CONTACT_FOUND,
        PipelineStatus.QUALIFIED,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.NO_WEBSITE: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.RESPONSIBLE_FOUND,
        PipelineStatus.CONTACT_FOUND,
        PipelineStatus.QUALIFIED,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.RESPONSIBLE_FOUND: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.CONTACT_FOUND,
        PipelineStatus.QUALIFIED,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.CONTACT_FOUND: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.QUALIFIED,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.QUALIFIED: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.READY_FOR_REVIEW,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.READY_FOR_REVIEW: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.CONTACTED,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.CONTACTED: {
        PipelineStatus.WAITING_REPLY,
        PipelineStatus.RESPONDED,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.WAITING_REPLY: {
        PipelineStatus.RESPONDED,
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.RESPONDED: {
        PipelineStatus.INTERESTED_HANDOFF,
        PipelineStatus.NOT_INTERESTED,
        PipelineStatus.NOT_RESPONSIBLE,
        PipelineStatus.UNCERTAIN,
        PipelineStatus.DISCARDED,
    },
    PipelineStatus.INTERESTED_HANDOFF: {
        PipelineStatus.DISCARDED,
        PipelineStatus.UNCERTAIN,
    },
    PipelineStatus.NOT_INTERESTED: set(),
    PipelineStatus.NOT_RESPONSIBLE: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.DISCARDED,
    },
    PipelineStatus.DISCARDED: set(),
    PipelineStatus.UNCERTAIN: {
        PipelineStatus.RESEARCHING,
        PipelineStatus.DISCARDED,
    },
}
