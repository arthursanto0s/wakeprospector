"""Unit tests for Phase 2 (Research, Discovery, Company and Website Verification)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config import (
    ConfidenceLevel,
    PipelineStatus,
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.models import Source
from src.research import ResearchService


class TestPhase2Research(unittest.TestCase):
    """Validates candidate ingestion, deduplication merge, identity corroboration,

    and website status tracking.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_research.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.service = ResearchService(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ingest_unique_candidate(self):
        src = Source(
            url="https://telelistas.net/empresa/vet-amigo",
            title="Telelistas - Vet Amigo",
            source_type=SourceType.E3,
            supports=["Descoberta de veterinária em Niterói"],
        )
        lead, is_new, reason = self.service.ingest_candidate(
            name="Clínica Veterinária Amigo Fiel",
            city="Niterói",
            category="Veterinária",
            neighborhood="Icaraí",
            phone="(21) 98765-1111",
            initial_source=src,
        )

        self.assertTrue(is_new)
        self.assertIsNone(reason)
        self.assertEqual(lead.pipeline_status, PipelineStatus.NEW)
        self.assertEqual(len(lead.sources), 1)
        self.assertEqual(lead.sources[0].url, src.url)

    def test_ingest_duplicate_merges_sources_t01(self):
        """T01 — Duplicate: Same company found from two sources must become one lead with multiple sources."""
        src1 = Source(
            url="https://guiamais.com.br/empresa1",
            title="Guia Mais - Vet Barreto",
            source_type=SourceType.E3,
            supports=["Primeira menção"],
        )
        lead1, is_new1, _ = self.service.ingest_candidate(
            name="Veterinária Barreto",
            city="Niterói",
            category="Veterinária",
            phone="(21) 2717-0000",
            initial_source=src1,
        )
        self.assertTrue(is_new1)

        src2 = Source(
            url="https://apontador.com.br/empresa1",
            title="Apontador - Vet Barreto",
            source_type=SourceType.E3,
            supports=["Segunda menção"],
        )
        lead2, is_new2, reason = self.service.ingest_candidate(
            name="Veterinária Barreto Ltda",
            city="Niterói",
            category="Veterinária",
            phone="2127170000",
            initial_source=src2,
        )

        # Must not create a second lead
        self.assertFalse(is_new2)
        self.assertEqual(lead1.id, lead2.id)
        self.assertIn("PHONE_MATCH", reason)

        # Lead in database must have both sources
        retrieved = self.db.get_lead(lead1.id)
        self.assertEqual(len(retrieved.sources), 2)
        urls = {s.url for s in retrieved.sources}
        self.assertIn(src1.url, urls)
        self.assertIn(src2.url, urls)

    def test_verify_company_identity(self):
        lead, _, _ = self.service.ingest_candidate(
            name="Adega do Vinho",
            city="São Gonçalo",
            category="Bebidas",
        )
        corroborating_source = Source(
            url="https://registro.oficial/cnpj/123",
            title="Registro Oficial de Empresas",
            source_type=SourceType.E1,
            supports=["Confirmação de endereço e CNPJ ativo"],
        )
        verified_lead = self.service.verify_company_identity(
            lead_id=lead.id,
            source=corroborating_source,
            confirmed_address="Rua Principal, 500",
            confirmed_neighborhood="Centro",
        )

        self.assertEqual(verified_lead.pipeline_status, PipelineStatus.VERIFIED)
        self.assertEqual(verified_lead.business.address, "Rua Principal, 500")
        self.assertEqual(verified_lead.business.neighborhood, "Centro")

    def test_website_verification_website_found_excluded_t04(self):
        """T04 — Existing website: Company has official domain.

        Expected: WEBSITE_FOUND and excluded from V1 target queue.
        """
        lead, _, _ = self.service.ingest_candidate(
            name="Hospital Veterinário Niterói",
            city="Niterói",
            category="Hospital Veterinário",
        )
        src = Source(
            url="https://hospitalvetniteroi.com.br",
            title="Site Oficial do Hospital",
            source_type=SourceType.E1,
            supports=["Site próprio ativo"],
        )
        updated_lead = self.service.record_website_verification(
            lead_id=lead.id,
            website_url="https://hospitalvetniteroi.com.br",
            website_status=WebsiteStatus.WEBSITE_FOUND,
            evidence_source=src,
        )

        self.assertEqual(
            updated_lead.business.website_status, WebsiteStatus.WEBSITE_FOUND
        )
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.DISCARDED
        )
        self.assertIn("hospitalvetniteroi.com.br", updated_lead.discard_reason)
        self.assertIn("excluída do foco V1", updated_lead.discard_reason)

    def test_website_verification_directory_or_social_is_not_own_website_t05(
        self,
    ):
        """T05 — Directory/Social only: Company exists only in directory/Instagram profile.

        Expected: no own website inferred, saved to digital_presence.
        """
        lead, _, _ = self.service.ingest_candidate(
            name="Pet Shop Charitas",
            city="Niterói",
            category="Pet Shop",
        )

        # Attempt to pass an Instagram profile as website
        updated_lead = self.service.record_website_verification(
            lead_id=lead.id,
            website_url="https://www.instagram.com/petshopcharitas",
            website_status=WebsiteStatus.WEBSITE_FOUND,  # incorrect flag passed
            notes="Perfil encontrado na bio",
        )

        # It must NOT be treated as own website
        self.assertEqual(updated_lead.business.website, "")
        self.assertEqual(
            updated_lead.digital_presence.instagram,
            "https://www.instagram.com/petshopcharitas",
        )
        # Status converted to NO_WEBSITE_FOUND
        self.assertEqual(
            updated_lead.business.website_status, WebsiteStatus.NO_WEBSITE_FOUND
        )
        self.assertEqual(
            updated_lead.pipeline_status, PipelineStatus.NO_WEBSITE
        )

    def test_website_verification_no_website_confirmed(self):
        lead, _, _ = self.service.ingest_candidate(
            name="Marcenaria Souza",
            city="Niterói",
            category="Marcenaria",
        )
        updated = self.service.record_website_verification(
            lead_id=lead.id,
            website_url="",
            website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            notes="Buscas exaustivas no Google, Maps e redes sociais confirmam ausência de site próprio.",
        )

        self.assertEqual(
            updated.business.website_status, WebsiteStatus.NO_WEBSITE_CONFIRMED
        )
        self.assertEqual(updated.pipeline_status, PipelineStatus.NO_WEBSITE)

    def test_log_research_query(self):
        entry = self.service.log_research_query(
            query="veterinarias em niteroi icaraí",
            purpose="Descoberta inicial de candidatos no bairro Icaraí",
        )
        self.assertEqual(entry.event_type, "RESEARCH_QUERY")
        self.assertEqual(
            entry.details["query"], "veterinarias em niteroi icaraí"
        )

        logs = self.db.list_audit_logs()
        queries = [
            l
            for l in logs
            if l.event_type == "RESEARCH_QUERY"
            and l.details.get("query") == "veterinarias em niteroi icaraí"
        ]
        self.assertEqual(len(queries), 1)


if __name__ == "__main__":
    unittest.main()
