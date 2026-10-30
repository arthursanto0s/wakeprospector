"""Unit tests for Phase 5 (Review Interface) and Phase 6 (Conversation, Intent Analysis, and Human Handoff)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config import (
    ConfidenceLevel,
    ContactType,
    OpportunityClass,
    PipelineStatus,
    ResponseIntent,
    WebsiteStatus,
)
from src.conversation import ConversationService
from src.database import DatabaseManager
from src.models import Business, Contact, Lead, Opportunity, Outreach
from src.review import ReviewService


class TestPhase5And6ReviewAndConversation(unittest.TestCase):
    """Validates T09 (Interest Handoff), T10 (Refusal), human send confirmation,

    review queue sorting, and HTML export.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_p56.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.review_service = ReviewService(db=self.db)
        self.conv_service = ConversationService(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_review_queue_sorting(self):
        """Validates that READY_FOR_REVIEW queue presents STRONG leads before POSSIBLE leads."""
        lead_possible = Lead(
            business=Business(name="Pet B", city="Niterói"),
            opportunity=Opportunity(classification=OpportunityClass.POSSIBLE),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        lead_strong = Lead(
            business=Business(name="Pet A", city="Niterói"),
            opportunity=Opportunity(classification=OpportunityClass.STRONG),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead_possible)
        self.db.save_lead(lead_strong)

        queue = self.review_service.get_review_queue()
        self.assertEqual(len(queue), 2)
        # STRONG must come first
        self.assertEqual(queue[0].business.name, "Pet A")
        self.assertEqual(queue[1].business.name, "Pet B")

    def test_export_html_report(self):
        """Validates generation of the standalone review HTML report."""
        lead = Lead(
            business=Business(name="Pet Star", city="Niterói"),
            contacts=[Contact(name="Carlos", phone="(21) 98765-4321")],
            outreach=Outreach(opening_message="Bom dia, Carlos!"),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead)

        out_path = Path(self.temp_dir) / "report.html"
        generated = self.review_service.export_html_report(out_path)
        self.assertTrue(generated.exists())
        content = generated.read_text(encoding="utf-8")
        self.assertIn("Pet Star", content)
        self.assertIn("Carlos", content)
        self.assertIn("wa.me", content)

    def test_human_send_confirmation(self):
        """Validates transition from READY_FOR_REVIEW to CONTACTED and WAITING_REPLY on manual confirm."""
        lead = Lead(
            business=Business(name="Adega Niterói", city="Niterói"),
            contacts=[Contact(phone="21999991111")],
            outreach=Outreach(opening_message="Bom dia!"),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead)

        updated = self.conv_service.confirm_manual_send(
            lead_id=lead.id,
            sent_message="Bom dia! Falo com o responsável?",
            notes="Enviado às 10:30 via WhatsApp pessoal.",
        )

        self.assertEqual(updated.pipeline_status, PipelineStatus.WAITING_REPLY)
        convs = self.db.list_conversations(lead.id)
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0].direction, "OUTBOUND")
        self.assertIn("Bom dia!", convs[0].text)

    def test_interest_handoff_t09(self):
        """T09 — Interest: User supplies a response showing meaningful interest.

        Expected: INTERESTED_HANDOFF and no autonomous continuation + executive dossier.
        """
        contact = Contact(
            name="Roberto Souza",
            role="Proprietário",
            phone="21987654321",
            type=ContactType.PERSONAL_PROFESSIONAL,
            confidence=ConfidenceLevel.HIGH,
        )
        lead = Lead(
            business=Business(
                name="Veterinária Souza",
                city="Niterói",
                category="Veterinária",
            ),
            contacts=[contact],
            opportunity=Opportunity(
                classification=OpportunityClass.STRONG,
                hypothesis="Site centralizaria agendamentos e catálogo.",
                evidence=["Catálogo ativo no Instagram", "Pedidos no WhatsApp"],
            ),
            outreach=Outreach(recommended_contact_id=contact.id),
            pipeline_status=PipelineStatus.WAITING_REPLY,
        )
        self.db.save_lead(lead)

        response_text = (
            "Olá, sou o Roberto sim! Tenho interesse, como funciona o orçamento de vocês?"
        )
        updated_lead, conv, handoff_dossier = (
            self.conv_service.process_inbound_response(
                lead_id=lead.id,
                text=response_text,
            )
        )

        self.assertEqual(conv.intent, ResponseIntent.INTERESTED)
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.INTERESTED_HANDOFF
        )
        self.assertIsNotNone(handoff_dossier)
        self.assertIn("DOSSIÊ DE HANDOFF COMERCIAL", handoff_dossier)
        self.assertIn("Roberto Souza", handoff_dossier)
        self.assertIn("Veterinária Souza", handoff_dossier)
        self.assertIn("O AGENTE ENCERRARÁ QUALQUER ABORDAGEM AUTÔNOMA", handoff_dossier)

    def test_refusal_not_interested_t10(self):
        """T10 — Refusal: Response declines.

        Expected: NOT_INTERESTED and no pressure sequence.
        """
        lead = Lead(
            business=Business(name="Barbearia Silva", city="Niterói"),
            pipeline_status=PipelineStatus.WAITING_REPLY,
        )
        self.db.save_lead(lead)

        response_text = "Boa tarde. Não temos interesse, obrigado!"
        updated_lead, conv, handoff = (
            self.conv_service.process_inbound_response(
                lead_id=lead.id,
                text=response_text,
            )
        )

        self.assertEqual(conv.intent, ResponseIntent.NOT_INTERESTED)
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.NOT_INTERESTED
        )
        self.assertIsNone(handoff)

    def test_wrong_person_not_responsible(self):
        lead = Lead(
            business=Business(name="Padaria Central", city="Niterói"),
            pipeline_status=PipelineStatus.WAITING_REPLY,
        )
        self.db.save_lead(lead)

        response_text = "Número errado, não trabalho mais nessa padaria."
        updated_lead, conv, _ = self.conv_service.process_inbound_response(
            lead_id=lead.id,
            text=response_text,
        )

        self.assertEqual(conv.intent, ResponseIntent.NOT_RESPONSIBLE)
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.NOT_RESPONSIBLE
        )


if __name__ == "__main__":
    unittest.main()
