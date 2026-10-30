"""Conversation management, intent classification, and human handoff service (Phase 6).

Enforces:
- 100% human confirmation before marking CONTACTED.
- Automated intent classification for incoming prospect replies.
- T09: Immediate handoff to human on meaningful interest (INTERESTED_HANDOFF) with context dossier.
- T10: Immediate cessation of outreach on refusal (NOT_INTERESTED).
- Distinction between responsible, wrong person, context questions, and refusals.
"""

import re
from typing import Optional, Tuple

from src.config import PipelineStatus, ResponseIntent
from src.database import DatabaseManager
from src.deduplication import normalize_text
from src.logger import get_logger, log_event
from src.models import Contact, Conversation, Lead, utc_now_iso

logger = get_logger()

# Regex rules for deterministic intent classification (applied on normalized text without accents)
INTEREST_PATTERNS = re.compile(
    r"\b(tenho\s+interesse|temos\s+interesse|como\s+funciona|quanto\s+custa|valor|preco|orcamento|pode\s+mandar|quero\s+saber|vamos\s+conversar|tenho\s+sim|temos\s+sim|sim|pode\s+falar|gostaria\s+de\s+saber)\b",
    re.IGNORECASE,
)

MEETING_PATTERNS = re.compile(
    r"\b(reuniao|pode\s+ligar|me\s+liga|passa\s+aqui|vamos\s+agendar|marcar\s+um\s+horario|marcar\s+uma\s+conversa)\b",
    re.IGNORECASE,
)

REFUSAL_PATTERNS = re.compile(
    r"\b(nao\s+tenho\s+interesse|nao\s+temos\s+interesse|sem\s+interesse|nao\s+quero|nao\s+queremos|nao\s+preciso|nao\s+precisamos|obrigado\s+nao|obrigada\s+nao|favor\s+nao|ja\s+tenho|ja\s+temos|nao\s+obrigado|nao\s+obrigada)\b",
    re.IGNORECASE,
)

WRONG_PERSON_PATTERNS = re.compile(
    r"\b(nao\s+sou\s+o\s+dono|nao\s+sou\s+a\s+dona|nao\s+sou\s+responsavel|numero\s+errado|nao\s+trabalho\s+mais|ligou\s+errado|nao\s+sou\s+eu)\b",
    re.IGNORECASE,
)

ASKING_CONTEXT_PATTERNS = re.compile(
    r"\b(quem\s+e|de\s+onde\s+fala|qual\s+empresa|do\s+que\s+se\s+trata|como\s+conseguiu|o\s+que\s+deseja)\b",
    re.IGNORECASE,
)


def classify_response_intent(text: str) -> ResponseIntent:
    """Classifies inbound response text into standard response intents."""
    norm = normalize_text(text)
    if not norm:
        return ResponseIntent.UNCERTAIN

    if REFUSAL_PATTERNS.search(norm):
        return ResponseIntent.NOT_INTERESTED

    if WRONG_PERSON_PATTERNS.search(norm):
        return ResponseIntent.NOT_RESPONSIBLE

    if MEETING_PATTERNS.search(norm):
        return ResponseIntent.MEETING_REQUEST

    if INTEREST_PATTERNS.search(norm):
        return ResponseIntent.INTERESTED

    if ASKING_CONTEXT_PATTERNS.search(norm):
        return ResponseIntent.ASKING_CONTEXT

    return ResponseIntent.UNCERTAIN


class ConversationService:
    """Manages outreach confirmations, prospect replies, intent handling, and handoffs."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def confirm_manual_send(
        self,
        lead_id: str,
        sent_message: Optional[str] = None,
        notes: str = "",
    ) -> Lead:
        """Confirms that the human operator manually dispatched the WhatsApp message.

        Transitions status to CONTACTED (with user_confirmed=True) and then WAITING_REPLY.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        msg_text = sent_message or lead.outreach.opening_message

        # Record outbound conversation
        conv = Conversation(
            lead_id=lead.id,
            timestamp=utc_now_iso(),
            direction="OUTBOUND",
            text=msg_text,
            intent=ResponseIntent.UNCERTAIN,
            notes=notes or "Envio manual confirmado pelo operador humano.",
        )
        self.db.save_conversation(conv)

        # Transition status to CONTACTED
        lead = self.db.update_lead_status(
            lead.id,
            PipelineStatus.CONTACTED,
            user_confirmed=True,
            lead=lead,
        )

        # Transition to WAITING_REPLY
        lead = self.db.update_lead_status(
            lead.id,
            PipelineStatus.WAITING_REPLY,
            lead=lead,
        )

        log_entry = log_event(
            event_type="HUMAN_SEND_CONFIRMED",
            lead_id=lead.id,
            details={"message": msg_text, "status": lead.pipeline_status.value},
        )
        self.db.insert_audit_log(log_entry)
        return lead

    def process_inbound_response(
        self,
        lead_id: str,
        text: str,
        intent_override: Optional[ResponseIntent] = None,
        notes: str = "",
    ) -> Tuple[Lead, Conversation, Optional[str]]:
        """Processes an incoming message from the prospect.

        Enforces:
        - T09: Meaningful interest -> INTERESTED_HANDOFF + handoff dossier.
        - T10: Refusal -> NOT_INTERESTED + immediate stop.
        """
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        intent = intent_override or classify_response_intent(text)

        # Save conversation entry
        conv = Conversation(
            lead_id=lead.id,
            timestamp=utc_now_iso(),
            direction="INBOUND",
            text=text,
            intent=intent,
            notes=notes,
        )
        self.db.save_conversation(conv)

        # Advance status to RESPONDED first
        if lead.pipeline_status in (
            PipelineStatus.CONTACTED,
            PipelineStatus.WAITING_REPLY,
        ):
            lead = self.db.update_lead_status(
                lead.id, PipelineStatus.RESPONDED, lead=lead
            )

        handoff_dossier: Optional[str] = None

        if intent in (ResponseIntent.INTERESTED, ResponseIntent.MEETING_REQUEST):
            # T09: Explicit interest -> Hand off immediately to human
            lead = self.db.update_lead_status(
                lead.id,
                PipelineStatus.INTERESTED_HANDOFF,
                lead=lead,
            )
            handoff_dossier = self._generate_handoff_dossier(lead, text, intent)

        elif intent == ResponseIntent.NOT_INTERESTED:
            # T10: Refusal -> Mark NOT_INTERESTED, no pressure sequence
            lead = self.db.update_lead_status(
                lead.id,
                PipelineStatus.NOT_INTERESTED,
                lead=lead,
            )

        elif intent == ResponseIntent.NOT_RESPONSIBLE:
            lead = self.db.update_lead_status(
                lead.id,
                PipelineStatus.NOT_RESPONSIBLE,
                lead=lead,
            )

        log_entry = log_event(
            event_type="INBOUND_RESPONSE_PROCESSED",
            lead_id=lead.id,
            details={
                "intent": intent.value,
                "text": text,
                "final_status": lead.pipeline_status.value,
            },
        )
        self.db.insert_audit_log(log_entry)
        return lead, conv, handoff_dossier

    def _generate_handoff_dossier(
        self, lead: Lead, response_text: str, intent: ResponseIntent
    ) -> str:
        """Constructs an executive handoff dossier for the human salesperson upon interest."""
        target_contact: Optional[Contact] = None
        for c in lead.contacts:
            if c.id == lead.outreach.recommended_contact_id:
                target_contact = c
                break
        if not target_contact and lead.contacts:
            target_contact = lead.contacts[0]

        lines = [
            "=" * 65,
            f"DOSSIÊ DE HANDOFF COMERCIAL — LEAD INTERESSADO [{lead.id}]",
            "=" * 65,
            f"Empresa       : {lead.business.name}",
            f"Cidade/Bairro : {lead.business.city} ({lead.business.neighborhood or 'N/I'})",
            f"Responsável   : {target_contact.name if target_contact else 'N/I'} ({target_contact.role if target_contact else 'N/I'})",
            f"Telefone      : {target_contact.phone if target_contact else 'N/I'}",
            "-" * 65,
            f"RESPOSTA RECEBIDA [{intent.value}]:",
            f"\"{response_text}\"",
            "-" * 65,
            "CONTEXTO DE OPORTUNIDADE OBSERVADO:",
            f"Classificação : {lead.opportunity.classification.value}",
            f"Hipótese      : {lead.opportunity.hypothesis}",
        ]
        if lead.opportunity.evidence:
            lines.append("Evidências públicas comprovadas:")
            for ev in lead.opportunity.evidence:
                lines.append(f"  - {ev}")

        lines.append("-" * 65)
        lines.append("RECOMENDAÇÃO PARA O VENDEDOR HUMANO:")
        lines.append(
            "1. Responder com agilidade agradecendo o retorno."
        )
        lines.append(
            f"2. Focar na centralização da presença web citando os pontos observados ({lead.business.category or 'do negócio'})."
        )
        lines.append(
            "3. Propor uma breve demonstração ou conversa rápida de 10 minutos sem compromisso."
        )
        lines.append(
            "4. O AGENTE ENCERRARÁ QUALQUER ABORDAGEM AUTÔNOMA A PARTIR DESTE PONTO."
        )
        lines.append("=" * 65)
        return "\n".join(lines)
