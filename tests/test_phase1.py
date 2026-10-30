"""Unit tests for Phase 1 (Technical Foundation) of Wake Prospector."""

import json
import os
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
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.deduplication import (
    check_lead_duplicate,
    extract_domain,
    is_generic_domain,
    normalize_business_name,
    normalize_phone,
    normalize_text,
)
from src.models import (
    AuditLogEntry,
    Business,
    Contact,
    Conversation,
    DigitalPresence,
    Lead,
    Opportunity,
    Outreach,
    Source,
    generate_lead_id,
)


class TestModelsSerialization(unittest.TestCase):
    """Validates dataclass integrity and JSON conversion."""

    def test_lead_serialization_roundtrip(self):
        lead = Lead(
            business=Business(
                name="Veterinária Souza Ltda",
                category="Clínica Veterinária",
                city="Niterói",
                neighborhood="Icaraí",
                address="Rua Moreira César, 100",
                website="",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Roberto Souza",
                    role="Proprietário",
                    phone="(21) 98765-4321",
                    type=ContactType.BUSINESS,
                    confidence=ConfidenceLevel.HIGH,
                    evidence_ids=["SRC-001"],
                )
            ],
            digital_presence=DigitalPresence(
                instagram="https://instagram.com/vetsouza",
                google_maps="https://maps.google.com/?cid=12345",
            ),
            opportunity=Opportunity(
                classification=OpportunityClass.STRONG,
                evidence=[
                    "Instagram ativo com 4k seguidores",
                    "Pedidos de vacina via WhatsApp",
                ],
                hypothesis="Site centralizaria agendamentos e catálogo de exames.",
                uncertainties=["Não se sabe o volume diário de atendimentos."],
            ),
            outreach=Outreach(
                opening_message="Bom dia, Roberto! Tudo bem? Falo com você, responsável pela Veterinária Souza?",
                human_review=True,
            ),
            sources=[
                Source(
                    id="SRC-001",
                    url="https://instagram.com/vetsouza",
                    title="Instagram Oficial",
                    source_type=SourceType.E1,
                    supports=["Roberto Souza é proprietário", "Telefone de contato"],
                )
            ],
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )

        d = lead.to_dict()
        reconstructed = Lead.from_dict(d)

        self.assertEqual(lead.id, reconstructed.id)
        self.assertEqual(lead.business.name, reconstructed.business.name)
        self.assertEqual(
            lead.business.website_status, reconstructed.business.website_status
        )
        self.assertEqual(len(reconstructed.contacts), 1)
        self.assertEqual(reconstructed.contacts[0].name, "Roberto Souza")
        self.assertEqual(
            reconstructed.contacts[0].confidence, ConfidenceLevel.HIGH
        )
        self.assertEqual(
            reconstructed.opportunity.classification, OpportunityClass.STRONG
        )
        self.assertEqual(len(reconstructed.sources), 1)
        self.assertEqual(reconstructed.sources[0].source_type, SourceType.E1)


class TestDeduplication(unittest.TestCase):
    """Validates phone normalization, business name normalization, and deduplication criteria."""

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("(21) 98765-4321"), "5521987654321")
        self.assertEqual(normalize_phone("+55 (21) 2620-1234"), "552126201234")
        self.assertEqual(normalize_phone("21987654321"), "5521987654321")
        self.assertEqual(normalize_phone(""), "")

    def test_normalize_business_name(self):
        self.assertEqual(
            normalize_business_name("Clínica Veterinária Souza LTDA - ME"),
            "clinica veterinaria souza",
        )
        self.assertEqual(
            normalize_business_name("Padaria & Confeitaria Pão D'Ouro EIRELI"),
            "padaria confeitaria pao d ouro",
        )

    def test_domain_extraction(self):
        self.assertEqual(
            extract_domain("https://www.vetsouza.com.br/contato"),
            "vetsouza.com.br",
        )
        self.assertTrue(is_generic_domain("instagram.com"))
        self.assertTrue(is_generic_domain("maps.google.com"))
        self.assertFalse(is_generic_domain("vetsouza.com.br"))

    def test_duplicate_by_phone(self):
        lead1 = Lead(
            business=Business(name="Pet Care Icaraí", city="Niterói"),
            contacts=[Contact(phone="(21) 99999-8888")],
        )
        lead2 = Lead(
            business=Business(name="Petshop Novo", city="Niterói"),
            contacts=[Contact(phone="21999998888")],
        )
        res = check_lead_duplicate(lead2, [lead1])
        self.assertTrue(res.is_duplicate)
        self.assertEqual(res.confidence, ConfidenceLevel.HIGH)
        self.assertEqual(res.matched_lead_id, lead1.id)

    def test_duplicate_by_exact_name_and_city(self):
        lead1 = Lead(
            business=Business(name="Veterinária Central Ltda", city="Niterói")
        )
        lead2 = Lead(
            business=Business(name="Veterinária Central", city="Niterói")
        )
        res = check_lead_duplicate(lead2, [lead1])
        self.assertTrue(res.is_duplicate)
        self.assertEqual(res.confidence, ConfidenceLevel.HIGH)

    def test_no_duplicate_same_name_different_city(self):
        lead1 = Lead(
            business=Business(name="Veterinária Central", city="Niterói")
        )
        lead2 = Lead(
            business=Business(name="Veterinária Central", city="São Gonçalo")
        )
        res = check_lead_duplicate(lead2, [lead1])
        self.assertFalse(res.is_duplicate)


class TestDatabaseAndPipelineRules(unittest.TestCase):
    """Validates SQLite persistence, transition checks, and strict business rules."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_prospector.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_retrieve_lead(self):
        lead = Lead(
            business=Business(
                name="Adega Imperial",
                category="Bebidas",
                city="São Gonçalo",
                website_status=WebsiteStatus.NO_WEBSITE_FOUND,
            ),
            contacts=[
                Contact(name="Carlos Lima", role="Gerente", phone="21988887777")
            ],
            pipeline_status=PipelineStatus.NEW,
        )
        self.db.save_lead(lead)

        retrieved = self.db.get_lead(lead.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.business.name, "Adega Imperial")
        self.assertEqual(retrieved.business.city, "São Gonçalo")
        self.assertEqual(len(retrieved.contacts), 1)

    def test_valid_pipeline_transitions(self):
        lead = Lead(
            business=Business(name="Pet Pet", city="Niterói"),
            pipeline_status=PipelineStatus.NEW,
        )
        self.db.save_lead(lead)

        # NEW -> RESEARCHING -> VERIFIED -> NO_WEBSITE -> QUALIFIED -> READY_FOR_REVIEW
        self.db.update_lead_status(lead.id, PipelineStatus.RESEARCHING)
        self.db.update_lead_status(lead.id, PipelineStatus.VERIFIED)
        self.db.update_lead_status(lead.id, PipelineStatus.NO_WEBSITE)
        self.db.update_lead_status(lead.id, PipelineStatus.QUALIFIED)
        updated = self.db.update_lead_status(
            lead.id, PipelineStatus.READY_FOR_REVIEW
        )

        self.assertEqual(updated.pipeline_status, PipelineStatus.READY_FOR_REVIEW)

    def test_invalid_pipeline_transition_raises_error(self):
        lead = Lead(
            business=Business(name="Pet Pet", city="Niterói"),
            pipeline_status=PipelineStatus.NEW,
        )
        self.db.save_lead(lead)

        # NEW directly to CONTACTED is forbidden
        with self.assertRaises(ValueError):
            self.db.update_lead_status(lead.id, PipelineStatus.CONTACTED)

    def test_whatsapp_human_control_enforced(self):
        """Transition to CONTACTED MUST fail without explicit user_confirmed=True."""
        lead = Lead(
            business=Business(name="Barbearia Alfa", city="Niterói"),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead)

        # Attempt to mark CONTACTED without user_confirmed
        with self.assertRaises(ValueError) as ctx:
            self.db.update_lead_status(
                lead.id, PipelineStatus.CONTACTED, user_confirmed=False
            )
        self.assertIn("explicit user confirmation", str(ctx.exception))

        # With user_confirmed=True, it succeeds
        updated = self.db.update_lead_status(
            lead.id, PipelineStatus.CONTACTED, user_confirmed=True
        )
        self.assertEqual(updated.pipeline_status, PipelineStatus.CONTACTED)

    def test_discard_requires_mandatory_reason(self):
        """Transition to DISCARDED MUST fail if reason is empty."""
        lead = Lead(
            business=Business(name="Oficina Beta", city="Niterói"),
            pipeline_status=PipelineStatus.RESEARCHING,
        )
        self.db.save_lead(lead)

        # Without reason -> fails
        with self.assertRaises(ValueError) as ctx:
            self.db.update_lead_status(
                lead.id, PipelineStatus.DISCARDED, reason=""
            )
        self.assertIn("mandatory discard reason", str(ctx.exception))

        # With reason -> succeeds
        updated = self.db.update_lead_status(
            lead.id,
            PipelineStatus.DISCARDED,
            reason="Empresa encerrou atividades comerciais.",
        )
        self.assertEqual(updated.pipeline_status, PipelineStatus.DISCARDED)
        self.assertEqual(
            updated.discard_reason, "Empresa encerrou atividades comerciais."
        )

    def test_conversation_logging_and_retrieval(self):
        lead = Lead(
            business=Business(name="Restaurante Mar", city="Niterói"),
            pipeline_status=PipelineStatus.CONTACTED,
        )
        self.db.save_lead(lead)

        conv = Conversation(
            lead_id=lead.id,
            direction="INBOUND",
            text="Olá, sou o dono sim. Vocês fazem orçamento?",
            intent=ResponseIntent.INTERESTED,
            notes="Cliente interessado em criação de site para cardápio",
        )
        self.db.save_conversation(conv)

        history = self.db.list_conversations(lead.id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].intent, ResponseIntent.INTERESTED)
        self.assertIn("orçamento", history[0].text)

    def test_audit_logs_recorded(self):
        lead = Lead(
            business=Business(name="Floricultura Rosa", city="Niterói"),
            pipeline_status=PipelineStatus.NEW,
        )
        self.db.save_lead(lead)
        self.db.update_lead_status(lead.id, PipelineStatus.RESEARCHING)

        logs = self.db.list_audit_logs(lead.id)
        self.assertTrue(len(logs) >= 2)
        event_types = [l.event_type for l in logs]
        self.assertIn("LEAD_SAVED", event_types)
        self.assertIn("PIPELINE_STATUS_CHANGE", event_types)


if __name__ == "__main__":
    unittest.main()
