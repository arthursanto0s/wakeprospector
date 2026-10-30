"""Opportunity analysis, explainable qualification, and outreach preparation service (Phase 4).

Enforces:
- Explainable opportunity classification without artificial 0-100 scores (T07 & T08).
- Distinction between Fact, Inference, and Uncertainty.
- Proper outreach message tailoring (personalized if responsible known vs general if unknown).
- Transition to READY_FOR_REVIEW with mandatory human review flag.
"""

from datetime import datetime
import re
from typing import List, Optional, Tuple

from src.config import (
    ConfidenceLevel,
    OpportunityClass,
    PipelineStatus,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.logger import get_logger, log_event
from src.models import Contact, Lead
from src.responsible import ResponsibleService

logger = get_logger()

COMPOSITE_FIRST_NAMES = [
    "maria do carmo", "maria da graca", "maria da graça", "maria eduarda", "maria clara",
    "maria paula", "maria eunice", "maria fernanda", "maria luiza", "maria alice",
    "jose luiz", "josé luiz", "jose carlos", "josé carlos", "jose roberto", "josé roberto",
    "ana paula", "ana cristina", "ana carolina", "ana luiza", "ana claudia", "ana beatriz",
    "joao carlos", "joão carlos", "joao paulo", "joão paulo",
]

FEMININE_FIRST_NAMES = {
    "adriana", "alessandra", "alexandra", "aline", "ana", "andreia", "andréia", "anelisa",
    "anneliza", "maria", "paula", "munik", "camila", "roberta", "carla", "patricia",
    "patrícia", "fernanda", "juliana", "beatriz", "mariana", "luciana", "claudia", "cláudia",
    "renata", "bruna", "carolina", "larissa", "leticia", "letícia", "vanessa", "debora", "débora",
    "rose", "rosane", "rosangela", "rosângela", "laissa", "laíssa", "ida", "eunice",
    "cristiana", "cristiane", "marcella", "marcela", "erica", "érica", "sabrina", "tatiana",
    "raquel", "helena", "natalia", "natália", "priscila", "flavia", "flávia", "daniela",
    "gabriela", "isabela", "isabella", "bianca", "monica", "mônica", "viviane", "simone",
    "denise", "eliane", "silvia", "sílvia", "valeria", "valéria", "marta", "clara",
    "luiza", "luíza", "alice", "heloisa", "heloísa", "cecilia", "cecília", "livia", "lívia",
    "thais", "thaís", "iris", "íris", "raissa", "raíssa", "michele", "michelle", "karina",
    "carina", "kelly", "sueli", "regina", "vera", "sonia", "sônia", "cintia", "cíntia",
    "fabiana", "lucia", "lúcia", "ines", "inês", "carmen", "miriam", "míriam", "lilian", "lílian",
}

PARTNERSHIP_WORDS = {
    "alves", "mattos", "almeida", "cruz", "alonso", "marrocos", "albuquerque", "trigo",
    "alli", "campos", "alvarenga", "tavares", "costa", "silva", "aguiar", "vasconcelos",
    "monteiro", "borges", "marques", "ache", "cordeiro", "morisaki", "parada", "dannemann",
    "siemsen", "ch", "afpm", "a.g.", "a. alves",
}


def clean_spoken_company_name(raw_name: str) -> str:
    """Cleans legal entity suffixes and formatting to produce a natural spoken name."""
    if not raw_name:
        return "seu escritório"

    name = raw_name.strip()

    # Remove city/neighborhood noise
    name = re.sub(r"\s+em\s+Barra\s+da\s+Tijuca.*$", "", name, flags=re.IGNORECASE).strip()

    # Clean redundant 'advogado(a)' prefix if attached to name
    name = re.sub(r"^advogad[oa]\s+", "", name, flags=re.IGNORECASE).strip()

    # Normalize common legal suffixes
    name = re.sub(r"\s*-\s*sociedade\s+individual\s+de\s+advocacia\b", " Advocacia", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+sociedade\s+individual\s+de\s+advocacia\b", " Advocacia", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+sociedade\s+de\s+advogados\b", " Advogados", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*-\s*advogados\s+associados\b", " Advogados", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+advogados\s+associados\b", " Advogados", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+advogados\s+assoc\b", " Advogados", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+e\s+consultoria\s+jur[ií]dica\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(ltda|me|epp|eireli|s/?a)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*-\s*", " - ", name)
    name = " ".join(name.split()).strip()

    # Format casing if all-caps
    if name.isupper() and len(name) > 4:
        words = name.title().split()
        lowers = {"E", "De", "Da", "Do", "Dos", "Das"}
        name = " ".join(w.lower() if w in lowers else w for w in words)

    return name.rstrip("-,. ").strip()


def extract_first_name(full_name: str) -> str:
    """Extracts first name or composite first name (e.g. Maria do Carmo, José Luiz), stripping titles."""
    clean = re.sub(r"^(?:dr|dra|doutor|doutora)\.?\s+", "", full_name.strip(), flags=re.IGNORECASE)
    norm = clean.lower().strip()
    for comp in COMPOSITE_FIRST_NAMES:
        if norm.startswith(comp):
            parts = clean.strip().split()
            comp_parts_len = len(comp.split())
            return " ".join(parts[:comp_parts_len])

    tokens = clean.strip().split()
    return tokens[0] if tokens else ""


def is_individual_person(contact_name: str, contact_role: str = "") -> bool:
    """Determines whether a contact name represents a single human individual."""
    if not contact_name:
        return False
    name = contact_name.strip()
    if not name:
        return False

    lower = name.lower()

    # Explicit business / partnership / institutional keywords
    if any(s in lower for s in [
        "&", "/", "sociedade", "associados", "banca", "advocacia",
        "diretoria", "direção", "direcao", "coordenador", "coordenação", "coordenacao",
        "corpo clínico", "corpo clinico", "responsável", "responsavel",
        "gerência", "gerencia", "equipe", "administração", "administracao",
        "setor", "recepção", "recepcao", "central", "atendimento",
    ]):
        return False

    # Check if role clearly indicates multiple partners or entity
    if contact_role and any(r in contact_role.lower() for r in ["sócios", "socios", "empresa", "institucional"]):
        return False

    clean_lower = re.sub(r"^(?:dr|dra|doutor|doutora)\.?\s+", "", lower, flags=re.IGNORECASE).strip()
    if not clean_lower:
        return False

    tokens = clean_lower.split()
    first_token = tokens[0].replace(".", "")

    # Initials like "A.G." or known partnership surnames
    if len(first_token) < 3 or first_token in PARTNERSHIP_WORDS:
        return False

    # Check for " e " connector: partnerships typically 2 or 3 tokens ("Alves e Mendonça")
    if " e " in clean_lower and len(tokens) <= 3:
        return False

    return True


def detect_gender(first_name: str, raw_contact_name: str = "", role: str = "") -> str:
    """Returns 'F' for feminine names/titles/roles, 'M' otherwise."""
    if raw_contact_name and re.search(r"^(?:dra|doutora)\b", raw_contact_name.strip(), flags=re.IGNORECASE):
        return "F"
    if raw_contact_name and re.search(r"^(?:dr|doutor)\b", raw_contact_name.strip(), flags=re.IGNORECASE):
        return "M"
    if role and any(k in role.lower() for k in ["médica", "medica", "sócia", "socia", "proprietária", "proprietaria", "advogada", "diretora", "administradora", "coordenadora"]):
        return "F"
    if not first_name.strip():
        return "M"
    first = first_name.strip().split()[0].lower().replace(".", "")
    if first in FEMININE_FIRST_NAMES or (first.endswith("a") and first not in {"luca", "juca", "borba"}):
        return "F"
    return "M"


def is_legal_business(lead: Lead) -> bool:
    """Returns True if the business belongs to the legal sector."""
    company = (lead.business.name or "").lower()
    category = (lead.business.category or "").lower()
    return any(k in company or k in category for k in ["advoc", "advog", "jurídic", "juridic", "direito", "lei", "law"])


def get_business_article(company_name: str) -> str:
    """Returns 'pela' if company starts with or implies a feminine noun, else 'pelo'."""
    if not company_name or not company_name.strip():
        return "pela"
    lower_full = company_name.strip().lower()
    first_word = lower_full.split()[0]
    first_word = re.sub(r"[^\w]", "", first_word)

    masculine_keywords = {
        "consultório", "consultorio", "centro", "hospital", "espaço", "espaco",
        "spa", "pet", "instituto", "laboratório", "laboratorio", "pronto",
        "ponto", "mundo", "bicho", "zoo", "grupo", "núcleo", "nucleo", "escritório", "escritorio",
    }
    if first_word in masculine_keywords:
        return "pelo"

    feminine_keywords = {
        "veterinária", "veterinaria", "clínica", "clinica", "loja", "farmácia", "farmacia",
        "imobiliária", "imobiliaria", "autoescola", "padaria", "oficina", "academia",
        "escola", "pizzaria", "hamburgueria", "consultoria", "agência", "agencia",
        "ótica", "otica", "confeitaria", "adega", "papelaria", "empresa", "sociedade",
        "casa", "boutique", "rede", "equipe", "unidade",
    }
    if first_word in feminine_keywords:
        return "pela"
    words_clean = [re.sub(r"[^\w]", "", w) for w in lower_full.split()]
    if any(w in {"centro", "consultório", "consultorio", "hospital", "laboratório", "laboratorio", "espaço", "espaco", "instituto", "núcleo", "nucleo", "diagnóstico", "diagnostico"} for w in words_clean):
        return "pelo"
    if any(k in lower_full for k in ["clínica", "clinica", "veterinária", "veterinaria", "oftalmologia", "cardiologia", "dermatologia", "ultrassonografia", "reabilitação", "reabilitacao"]):
        return "pela"
    if first_word in FEMININE_FIRST_NAMES or (first_word.endswith("a") and first_word not in {"dia", "cinema", "sistema", "idioma", "tema", "mapa"}):
        return "pela"
    return "pelo"


def get_time_greeting(hour: Optional[int] = None) -> str:
    """Returns 'Bom dia', 'Boa tarde', or 'Boa noite' based on the current hour."""
    if hour is None:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def build_professional_outreach(
    lead: Lead,
    target_contact: Optional[Contact] = None,
    hour: Optional[int] = None,
) -> str:
    """Generates direct time-aware WhatsApp outreach message for the responsible person."""
    greeting = get_time_greeting(hour)
    company_raw = lead.business.name or ""
    clean_company = clean_spoken_company_name(company_raw)

    if not target_contact:
        if lead.outreach.recommended_contact_id:
            for c in lead.contacts:
                if c.id == lead.outreach.recommended_contact_id:
                    target_contact = c
                    break
        if not target_contact and lead.contacts:
            target_contact = lead.contacts[0]

    contact_name = target_contact.name if target_contact else ""
    contact_role = target_contact.role if target_contact else ""

    is_person = is_individual_person(contact_name, contact_role)
    legal = is_legal_business(lead)

    if is_person:
        first_name = extract_first_name(contact_name)
        gender = detect_gender(first_name, contact_name, contact_role)
        honorific = "Dra." if gender == "F" else "Dr."

        has_dr_title = bool(re.search(r"^(?:dr|dra|doutor|doutora)\b", contact_name.strip(), flags=re.IGNORECASE))
        is_vet_doctor = any(k in contact_role.lower() for k in ["médic", "medic", "crmv", "veterinári", "veterinari", "cirurgi", "odontolog", "cardiolog", "dermatolog"])
        is_clinic_category = any(k in (lead.business.category or "").lower() for k in ["veterin", "clínica", "clinica", "médic", "medic", "odonto"])

        if legal or has_dr_title or is_vet_doctor or is_clinic_category:
            return f"{greeting}, {honorific} {first_name}, tudo bem?"
        return f"{greeting}, {first_name}, tudo bem?"

    # Institutional / clinic contact when no individual person is identified
    if legal:
        return f"{greeting}! Gostaria de falar com o responsável pelo escritório {clean_company}."
    article = get_business_article(clean_company)
    return f"{greeting}! Gostaria de falar com o responsável {article} {clean_company}."


def build_clinic_fallback_outreach(
    lead: Lead,
    owner_contact: Optional[Contact] = None,
    hour: Optional[int] = None,
) -> str:
    """Generates a time-aware fallback WhatsApp message for the clinic's general/reception channel."""
    greeting = get_time_greeting(hour)
    company_raw = lead.business.name or ""
    clean_company = clean_spoken_company_name(company_raw)
    if is_legal_business(lead):
        return f"{greeting}! Gostaria de falar com o responsável pelo escritório {clean_company}."
    article = get_business_article(clean_company)
    return f"{greeting}! Gostaria de falar com o responsável {article} {clean_company}."



class OpportunityService:
    """Provides qualification logic, opportunity rationale, and outreach generation."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.responsible_service = ResponsibleService(db=self.db)

    def qualify_lead(
        self,
        lead_id: str,
        evidence: List[str],
        hypothesis: str = "",
        uncertainties: Optional[List[str]] = None,
        classification: Optional[OpportunityClass] = None,
    ) -> Lead:
        """Qualifies a lead based on observed public evidence without artificial precision.

        Enforces:
        - T07: Active digital business + no site + commercial signals -> STRONG or POSSIBLE with rationale.
        - T08: Sparse or absent evidence -> UNCERTAIN or LOW_PRIORITY, never invented.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        clean_evidence = [e.strip() for e in evidence if e.strip()]
        clean_uncertainties = [u.strip() for u in (uncertainties or []) if u.strip()]

        # Deterministic classification logic if not explicitly provided
        if classification is None:
            if not clean_evidence:
                # T08: sparse or no evidence
                classification = OpportunityClass.LOW_PRIORITY
                if not hypothesis:
                    hypothesis = "Poucas evidências públicas encontradas sobre a operação comercial ou demanda de presença web."
            else:
                has_usable_contact = any(bool(c.phone) for c in lead.contacts)
                no_website = lead.business.website_status in (
                    WebsiteStatus.NO_WEBSITE_CONFIRMED,
                    WebsiteStatus.NO_WEBSITE_FOUND,
                )

                if len(clean_evidence) >= 2 and no_website and has_usable_contact:
                    # T07: multiple verified signals
                    classification = OpportunityClass.STRONG
                elif len(clean_evidence) >= 1 and no_website:
                    classification = OpportunityClass.POSSIBLE
                else:
                    classification = OpportunityClass.UNCERTAIN

        lead.opportunity.classification = classification
        lead.opportunity.evidence = clean_evidence
        lead.opportunity.hypothesis = hypothesis
        if clean_uncertainties:
            lead.opportunity.uncertainties.extend(clean_uncertainties)

        # Save lead state
        lead = self.db.save_lead(lead)

        # Advance pipeline status to QUALIFIED if eligible
        if lead.pipeline_status in (
            PipelineStatus.NEW,
            PipelineStatus.RESEARCHING,
            PipelineStatus.VERIFIED,
            PipelineStatus.NO_WEBSITE,
            PipelineStatus.RESPONSIBLE_FOUND,
            PipelineStatus.CONTACT_FOUND,
        ):
            # Advance deterministically to QUALIFIED
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
                    lead.id, PipelineStatus.QUALIFIED, lead=lead
                )
            elif lead.pipeline_status in (
                PipelineStatus.RESPONSIBLE_FOUND,
                PipelineStatus.CONTACT_FOUND,
            ):
                lead = self.db.update_lead_status(
                    lead.id, PipelineStatus.QUALIFIED, lead=lead
                )

        log_entry = log_event(
            event_type="LEAD_QUALIFIED",
            lead_id=lead.id,
            details={
                "classification": classification.value,
                "evidence_count": len(clean_evidence),
                "hypothesis": hypothesis,
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead

    def prepare_outreach(self, lead_id: str) -> Tuple[Lead, str]:
        """Prepares opening outreach message according to manual guidelines:

        - If responsible person is known with good confidence:
          "Bom dia, [Nome]! Tudo bem? Falo com você, responsável pela [Empresa]?"
        - If responsible is unknown or uncertain:
          "Bom dia! Tudo bem? Falo com o responsável pela [Empresa]?"

        Sets human_review=True and advances pipeline status to READY_FOR_REVIEW.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        # Ensure recommended contact is set
        if not lead.outreach.recommended_contact_id:
            lead, _ = self.responsible_service.select_recommended_contact(lead.id)

        target_contact = None
        for c in lead.contacts:
            if c.id == lead.outreach.recommended_contact_id:
                target_contact = c
                break

        # Check if responsible name is reliably known
        is_name_confident = (
            target_contact
            and target_contact.name
            and target_contact.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        )

        opening_message = build_professional_outreach(lead, target_contact)
        lead.outreach.opening_message = opening_message
        lead.outreach.human_review = True

        # Save lead state
        lead = self.db.save_lead(lead)

        # Advance pipeline status to READY_FOR_REVIEW
        if lead.pipeline_status in (
            PipelineStatus.NEW,
            PipelineStatus.RESEARCHING,
            PipelineStatus.VERIFIED,
            PipelineStatus.NO_WEBSITE,
            PipelineStatus.RESPONSIBLE_FOUND,
            PipelineStatus.CONTACT_FOUND,
            PipelineStatus.QUALIFIED,
        ):
            lead = self.db.update_lead_status(
                lead.id, PipelineStatus.READY_FOR_REVIEW, lead=lead
            )

        log_entry = log_event(
            event_type="OUTREACH_PREPARED",
            lead_id=lead.id,
            details={
                "opening_message": opening_message,
                "is_name_confident": is_name_confident,
                "target_contact_id": (
                    target_contact.id if target_contact else None
                ),
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead, opening_message
