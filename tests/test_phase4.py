"""Unit tests for Phase 4 (Opportunity Analysis, Qualification, and Outreach Preparation)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config import (
    ConfidenceLevel,
    ContactType,
    OpportunityClass,
    PipelineStatus,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.models import Business, Contact, Lead
from src.qualification import (
    OpportunityService,
    build_clinic_fallback_outreach,
    build_professional_outreach,
    get_time_greeting,
)


class TestPhase4Qualification(unittest.TestCase):
    """Validates T07 (Strong Opportunity), T08 (Sparse Evidence / Low Priority),

    message drafting personalization, and transition to READY_FOR_REVIEW.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_phase4.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.service = OpportunityService(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_strong_opportunity_t07(self):
        """T07 — Strong opportunity: Active digital business, no site, commercial signals.

        Expected: STRONG with evidence-based hypothesis.
        """
        lead = Lead(
            business=Business(
                name="Adega São Gonçalo",
                category="Bebidas",
                city="São Gonçalo",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Marcos Silva",
                    role="Proprietário",
                    phone="(21) 97777-6666",
                    type=ContactType.PERSONAL_PROFESSIONAL,
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            pipeline_status=PipelineStatus.CONTACT_FOUND,
        )
        self.db.save_lead(lead)

        evidence = [
            "Catálogo de bebidas atualizado semanalmente no Instagram Stories",
            "Pedidos e entrega expressa direcionados exclusivamente para o WhatsApp",
            "Postagens diárias e engajamento comercial ativo com clientes locais",
        ]
        hypothesis = (
            "Um site próprio com catálogo integrado centralizaria a apresentação dos produtos, "
            "reduziria o atrito no atendimento e organizaria os pedidos de entrega."
        )
        uncertainties = ["Não foi possível estimar o volume diário de vendas."]

        qualified_lead = self.service.qualify_lead(
            lead_id=lead.id,
            evidence=evidence,
            hypothesis=hypothesis,
            uncertainties=uncertainties,
        )

        self.assertEqual(
            qualified_lead.opportunity.classification, OpportunityClass.STRONG
        )
        self.assertEqual(len(qualified_lead.opportunity.evidence), 3)
        self.assertIn("catálogo integrado", qualified_lead.opportunity.hypothesis)
        self.assertEqual(
            qualified_lead.pipeline_status, PipelineStatus.QUALIFIED
        )

    def test_no_evidence_sparse_t08(self):
        """T08 — No evidence: Sparse business presence.

        Expected: UNCERTAIN/LOW_PRIORITY, not invented.
        """
        lead = Lead(
            business=Business(
                name="Oficina Mecânica Desconhecida",
                category="Mecânica",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_FOUND,
            ),
            contacts=[],
            pipeline_status=PipelineStatus.NO_WEBSITE,
        )
        self.db.save_lead(lead)

        qualified_lead = self.service.qualify_lead(
            lead_id=lead.id,
            evidence=[],  # No evidence found
        )

        self.assertIn(
            qualified_lead.opportunity.classification,
            (OpportunityClass.LOW_PRIORITY, OpportunityClass.UNCERTAIN),
        )
        self.assertEqual(len(qualified_lead.opportunity.evidence), 0)
        self.assertIn(
            "Poucas evidências públicas", qualified_lead.opportunity.hypothesis
        )

    def test_outreach_personalized_when_responsible_known(self):
        """Generates tailored opening with first name when responsible is known."""
        lead = Lead(
            business=Business(
                name="Veterinária Souza",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Roberto Souza",
                    role="Proprietário",
                    phone="(21) 98765-4321",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            pipeline_status=PipelineStatus.QUALIFIED,
        )
        self.db.save_lead(lead)

        updated_lead, msg = self.service.prepare_outreach(lead.id)
        greeting = get_time_greeting()

        self.assertEqual(
            msg,
            f"{greeting}, Roberto, tudo bem?",
        )
        self.assertTrue(updated_lead.outreach.human_review)
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.READY_FOR_REVIEW
        )

    def test_outreach_general_when_responsible_unknown(self):
        """Generates institutional greeting when responsible is not known."""
        lead = Lead(
            business=Business(
                name="Pet Shop Central",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="",
                    role="Comercial",
                    phone="(21) 2620-0000",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            ],
            pipeline_status=PipelineStatus.QUALIFIED,
        )
        self.db.save_lead(lead)

        updated_lead, msg = self.service.prepare_outreach(lead.id)
        greeting = get_time_greeting()

        self.assertEqual(
            msg,
            f"{greeting}! Gostaria de falar com o responsável pelo Pet Shop Central.",
        )
        self.assertTrue(updated_lead.outreach.human_review)
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.READY_FOR_REVIEW
        )

    def test_outreach_legal_individual_with_honorific(self):
        """Generates legal opening with Dr./Dra. and time-of-day greeting."""
        lead = Lead(
            business=Business(
                name="Mariana Silva Sociedade Individual de Advocacia",
                category="Advocacia",
                city="Rio de Janeiro",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Mariana Silva",
                    role="Advogada Titular",
                    phone="(21) 98888-7777",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            pipeline_status=PipelineStatus.QUALIFIED,
        )
        self.db.save_lead(lead)

        updated_lead, msg = self.service.prepare_outreach(lead.id)
        greeting = get_time_greeting()

        self.assertEqual(
            msg,
            f"{greeting}, Dra. Mariana, tudo bem?",
        )

    def test_outreach_legal_partnership(self):
        """Generates respectful institutional inquiry for legal partnerships."""
        lead = Lead(
            business=Business(
                name="Albuquerque & Trigo Advogados Associados",
                category="Advocacia",
                city="Rio de Janeiro",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Albuquerque & Trigo",
                    role="Advogados Sócios",
                    confidence=ConfidenceLevel.MEDIUM,
                )
            ],
            pipeline_status=PipelineStatus.QUALIFIED,
        )
        self.db.save_lead(lead)

        updated_lead, msg = self.service.prepare_outreach(lead.id)
        greeting = get_time_greeting()

        self.assertEqual(
            msg,
            f"{greeting}! Gostaria de falar com o responsável pelo escritório Albuquerque & Trigo Advogados.",
        )


if __name__ == "__main__":
    unittest.main()
