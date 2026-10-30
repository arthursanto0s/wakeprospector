"""Unit tests for AdversarialLeadAudit (src/audit.py)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.audit import AdversarialAuditService, is_synthetic_or_corrupted_phone
from src.config import (
    ConfidenceLevel,
    ContactType,
    OpportunityClass,
    PipelineStatus,
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.models import Business, Contact, Lead, Opportunity, Outreach, Source


class TestAdversarialAudit(unittest.TestCase):
    """Validates phone collision detection, synthetic/corrupted phone rejection,
    and dialectical adversarial audit enforcement.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_audit.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.audit_svc = AdversarialAuditService(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_synthetic_or_corrupted_phone_detection(self):
        # Valid Brazilian mobile
        bad, _ = is_synthetic_or_corrupted_phone("(21) 99493-5808")
        self.assertFalse(bad)

        # Valid Brazilian landline
        bad, _ = is_synthetic_or_corrupted_phone("(21) 2493-0619")
        self.assertFalse(bad)

        # Corrupted landline with artificial '9' prepended (9 + 2493...)
        bad, reason = is_synthetic_or_corrupted_phone("(21) 92493-0619")
        self.assertTrue(bad)
        self.assertIn("fixo corrompido", reason)

        # Sequential fake mobile
        bad, reason = is_synthetic_or_corrupted_phone("(21) 99123-4567")
        self.assertTrue(bad)
        self.assertIn("sequencial/sintético", reason)

        bad2, reason2 = is_synthetic_or_corrupted_phone("(21) 99876-5432")
        self.assertTrue(bad2)
        self.assertIn("sequencial/sintético", reason2)

    def test_phone_collision_across_two_leads_fails_audit(self):
        src = Source(
            url="https://instagram.com/clinica1",
            title="Instagram",
            source_type=SourceType.E1,
        )
        lead1 = Lead(
            business=Business(
                name="Clínica Alfa Vet",
                category="Clínica Veterinária",
                city="Rio de Janeiro",
                neighborhood="Barra da Tijuca",
                address="Av. das Américas, 1000",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Dr. Carlos Alfa",
                    role="Médico Veterinário",
                    phone="(21) 99493-5808",
                    type=ContactType.PERSONAL_PROFESSIONAL,
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            sources=[src],
            outreach=Outreach(
                opening_message="Olá, Dr. Carlos, tudo bem? Aqui é o Arthur da Wake. Falo com o responsável pela Clínica Alfa Vet?"
            ),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        lead2 = Lead(
            business=Business(
                name="Clínica Beta Vet",
                category="Clínica Veterinária",
                city="Rio de Janeiro",
                neighborhood="Barra da Tijuca",
                address="Av. das Américas, 2000",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Dra. Marina Beta",
                    role="Médica Veterinária",
                    phone="(21) 99493-5808",  # Duplicate phone!
                    type=ContactType.PERSONAL_PROFESSIONAL,
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            sources=[src],
            outreach=Outreach(
                opening_message="Olá, Dra. Marina, tudo bem? Aqui é o Arthur da Wake. Falo com a responsável pela Clínica Beta Vet?"
            ),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead1)
        self.db.save_lead(lead2)

        self.audit_svc.attach_adversarial_audit(
            lead1.id,
            phone_provenance="Extraído da bio oficial @alfavet",
            decision_maker_analysis="Dr. Carlos é sócio-administrador",
            adversarial_challenge="Verificado se não possui domínio próprio.",
            adversarial_verdict="Confirmado sem site e número exclusivo.",
        )
        self.audit_svc.attach_adversarial_audit(
            lead2.id,
            phone_provenance="Extraído de listagem",
            decision_maker_analysis="Dra. Marina é titular",
            adversarial_challenge="Checagem de unicidade",
            adversarial_verdict="Pendente",
        )

        summary = self.audit_svc.audit_all_leads()
        self.assertFalse(summary["all_passed"])
        self.assertEqual(summary["phone_collisions_count"], 1)
        self.assertEqual(summary["failed"], 2)

    def test_valid_audited_lead_passes(self):
        src = Source(
            url="https://linktr.ee/cats.vet",
            title="Linktree Oficial Cat's Vet",
            source_type=SourceType.E1,
        )
        lead = Lead(
            business=Business(
                name="Cat's Vet Barra da Tijuca",
                category="Clínica Veterinária",
                city="Rio de Janeiro",
                neighborhood="Barra da Tijuca",
                address="Av. das Américas, 7707",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Dr. Renaldo Ramos Nóbrega",
                    role="Médico Veterinário RT (CRMV-RJ 3263)",
                    phone="(21) 99493-5808",
                    type=ContactType.PERSONAL_PROFESSIONAL,
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            sources=[src],
            opportunity=Opportunity(
                classification=OpportunityClass.STRONG,
                hypothesis="Clínica exclusiva para felinos sem site próprio.",
                evidence=["Linktree oficial", "Instagram ativo"],
            ),
            outreach=Outreach(
                opening_message="Boa tarde, Dr. Renaldo, tudo bem?"
            ),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(lead)
        self.audit_svc.attach_adversarial_audit(
            lead_id=lead.id,
            phone_provenance="Link direto wa.me/5521994935808 extraído do Linktree oficial (linktr.ee/cats.vet) e Instagram @cats.vet.",
            decision_maker_analysis="Dr. Renaldo Ramos Nóbrega (CRMV-RJ 3263) é o fundador e responsável técnico.",
            adversarial_challenge="Contestação: Uma clínica 24h especializada em felinos na Av. das Américas já não teria um site próprio? O número (21) 99493-5808 é realmente exclusivo da unidade Barra?",
            adversarial_verdict="Refutado: A clínica utiliza exclusivamente linktr.ee/cats.vet na bio do Instagram (@cats.vet), onde os botões levam diretamente ao WhatsApp (21) 99493-5808 e localização no Maps, sem nenhum domínio próprio ativo.",
        )

        summary = self.audit_svc.audit_all_leads()
        self.assertTrue(summary["all_passed"])
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 0)


if __name__ == "__main__":
    unittest.main()
