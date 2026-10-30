"""Unit tests for Phase 3 (Responsible Identification, Contact Association, Evidence, and Confidence)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config import (
    ConfidenceLevel,
    ContactType,
    PipelineStatus,
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.models import Business, Contact, Lead, Source
from src.responsible import ResponsibleService


class TestPhase3Responsible(unittest.TestCase):
    """Validates T02 (False Owner), T03 (Phone Ambiguity), T06 (Conflicting Owner),

    pipeline transitions, and contact recommendation.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_responsible.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.service = ResponsibleService(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_false_owner_weak_evidence_t02(self):
        """T02 — False owner: Person shares company surname or appears in photo but no ownership evidence.

        Expected: not given high confidence, uncertainty note recorded.
        """
        lead = Lead(
            business=Business(
                name="Veterinária Souza",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            pipeline_status=PipelineStatus.NO_WEBSITE,
        )
        self.db.save_lead(lead)

        src = Source(
            url="https://instagram.com/p/123",
            title="Post de Instagram",
            source_type=SourceType.E4,
            supports=["Foto com menção"],
        )

        updated_lead, contact, has_conflict = self.service.add_responsible(
            lead_id=lead.id,
            name="Mariana Souza",
            role="Proprietário",
            source=src,
            relationship_proof="Aparece em foto no Instagram e possui o mesmo sobrenome da empresa",
            confidence=ConfidenceLevel.HIGH,  # Passed HIGH but should be degraded
        )

        self.assertFalse(has_conflict)
        # Confidence must be degraded to LOW
        self.assertEqual(contact.confidence, ConfidenceLevel.LOW)
        # Uncertainty must be explicitly recorded
        uncertainties_text = " ".join(updated_lead.opportunity.uncertainties)
        self.assertIn("T02", uncertainties_text)
        self.assertIn("indício fraco", uncertainties_text)
        # Pipeline should NOT advance to RESPONSIBLE_FOUND because evidence is weak
        self.assertEqual(updated_lead.pipeline_status, PipelineStatus.NO_WEBSITE)

    def test_phone_ambiguity_t03(self):
        """T03 — Phone ambiguity: Phone appears on company page but no person association.

        Expected: company contact (BUSINESS), not personal contact.
        """
        lead = Lead(
            business=Business(
                name="Veterinária Souza",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            pipeline_status=PipelineStatus.NO_WEBSITE,
        )
        self.db.save_lead(lead)

        src_owner = Source(
            url="https://cnpj.biz/123",
            title="Registro CNPJ",
            source_type=SourceType.E1,
            supports=["Sócio-administrador"],
        )
        updated_lead, contact, _ = self.service.add_responsible(
            lead_id=lead.id,
            name="Roberto Souza",
            role="Proprietário",
            source=src_owner,
            relationship_proof="Sócio-administrador no contrato social",
            confidence=ConfidenceLevel.HIGH,
        )

        # 1. Associate company phone without direct personal link
        src_phone = Source(
            url="https://maps.google.com/souza",
            title="Google Maps",
            source_type=SourceType.E2,
        )
        updated_lead, updated_contact = self.service.associate_phone(
            lead_id=updated_lead.id,
            contact_id=contact.id,
            phone="(21) 2620-1234",
            source=src_phone,
            is_person_associated=False,  # company channel only
        )

        self.assertEqual(updated_contact.type, ContactType.BUSINESS)
        uncertainties_text = " ".join(updated_lead.opportunity.uncertainties)
        self.assertIn("T03", uncertainties_text)
        self.assertIn("pertence aos canais da empresa", uncertainties_text)

        # 2. Now associate a confirmed direct professional phone
        src_personal_phone = Source(
            url="https://wa.me/5521999998888",
            title="WhatsApp Profissional Roberto Souza",
            source_type=SourceType.E1,
            supports=["Número direto de atendimento de Roberto"],
        )
        _, direct_contact = self.service.associate_phone(
            lead_id=updated_lead.id,
            contact_id=contact.id,
            phone="(21) 99999-8888",
            source=src_personal_phone,
            is_person_associated=True,
        )

        self.assertEqual(
            direct_contact.type, ContactType.PERSONAL_PROFESSIONAL
        )

    def test_conflicting_owner_t06(self):
        """T06 — Conflicting owner: Two sources name different responsible persons.

        Expected: conflict recorded, confidence reduced.
        """
        lead = Lead(
            business=Business(
                name="Clínica Veterinária Vida",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            pipeline_status=PipelineStatus.NO_WEBSITE,
        )
        self.db.save_lead(lead)

        src1 = Source(
            url="https://portal1.com/vida",
            title="Portal de Notícias Local",
            source_type=SourceType.E2,
        )
        lead, contact1, conflict1 = self.service.add_responsible(
            lead_id=lead.id,
            name="Dr. Fernando Alves",
            role="Diretor Clínico e Fundador",
            source=src1,
            relationship_proof="Fundador da clínica em matéria de jornal",
            confidence=ConfidenceLevel.HIGH,
        )
        self.assertFalse(conflict1)
        self.assertEqual(contact1.confidence, ConfidenceLevel.HIGH)

        # Second source presents a different person as owner
        src2 = Source(
            url="https://cnpj.com/vida",
            title="Consulta CNPJ",
            source_type=SourceType.E1,
        )
        lead, contact2, conflict2 = self.service.add_responsible(
            lead_id=lead.id,
            name="Juliana Ribeiro",
            role="Proprietária",
            source=src2,
            relationship_proof="Sócia majoritária no contrato social",
            confidence=ConfidenceLevel.HIGH,
        )

        self.assertTrue(conflict2)
        # Both contacts should now have LOW confidence due to conflict
        self.assertEqual(contact2.confidence, ConfidenceLevel.LOW)
        retrieved = self.db.get_lead(lead.id)
        self.assertEqual(retrieved.contacts[0].confidence, ConfidenceLevel.LOW)
        # Uncertainty must record the conflict explicitly
        uncertainties_text = " ".join(retrieved.opportunity.uncertainties)
        self.assertIn("CONFLITO DE RESPONSÁVEL (T06)", uncertainties_text)
        self.assertIn("Fernando Alves", uncertainties_text)
        self.assertIn("Juliana Ribeiro", uncertainties_text)

    def test_valid_responsible_and_pipeline_progression(self):
        lead = Lead(
            business=Business(
                name="Adega Niterói",
                city="Niterói",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            pipeline_status=PipelineStatus.NO_WEBSITE,
        )
        self.db.save_lead(lead)

        src = Source(
            url="https://registro.com/adega",
            title="Junta Comercial",
            source_type=SourceType.E1,
        )
        lead, contact, _ = self.service.add_responsible(
            lead_id=lead.id,
            name="André Gomes",
            role="Proprietário",
            source=src,
            relationship_proof="Sócio-administrador com 100% das cotas",
            confidence=ConfidenceLevel.HIGH,
        )

        self.assertEqual(lead.pipeline_status, PipelineStatus.RESPONSIBLE_FOUND)

        lead, contact = self.service.associate_phone(
            lead_id=lead.id,
            contact_id=contact.id,
            phone="(21) 98888-5555",
            is_person_associated=True,
        )

        self.assertEqual(lead.pipeline_status, PipelineStatus.CONTACT_FOUND)

    def test_select_recommended_contact(self):
        lead = Lead(
            business=Business(name="Pet Care", city="Niterói"),
            pipeline_status=PipelineStatus.CONTACT_FOUND,
        )
        # Generic company contact
        c1 = Contact(
            name="",
            role="Empresa",
            phone="2126200000",
            type=ContactType.BUSINESS,
            confidence=ConfidenceLevel.MEDIUM,
        )
        # Responsible person with personal professional phone
        c2 = Contact(
            name="Paula Silva",
            role="Proprietária",
            phone="21999997777",
            type=ContactType.PERSONAL_PROFESSIONAL,
            confidence=ConfidenceLevel.HIGH,
        )
        lead.contacts.extend([c1, c2])
        self.db.save_lead(lead)

        updated_lead, best = self.service.select_recommended_contact(lead.id)
        self.assertIsNotNone(best)
        self.assertEqual(best.id, c2.id)
        self.assertEqual(updated_lead.outreach.recommended_contact_id, c2.id)


if __name__ == "__main__":
    unittest.main()
