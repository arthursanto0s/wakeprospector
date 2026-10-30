"""Automated tests for Wake Prospector CRM HTTP Server and REST API."""

import json
import shutil
import tempfile
import threading
import unittest
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.config import PipelineStatus, WebsiteStatus
from src.database import DatabaseManager
from src.models import Business, Contact, Lead, Outreach
from src.server import CRMRequestHandler, ThreadingHTTPServer, run_server


class TestCRMServer(unittest.TestCase):
    """Integration test suite for the local CRM REST API."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = Path(cls.temp_dir) / "test_server.db"
        cls.db = DatabaseManager(db_path=cls.test_db_path)
        cls.db.init_db()
        CRMRequestHandler.db_override = cls.db

        # Seed a test lead in isolated database
        cls.test_lead = Lead(
            business=Business(
                name="Escritório Teste CRM",
                category="Advocacia",
                city="Rio de Janeiro",
                neighborhood="Barra da Tijuca",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
            ),
            contacts=[
                Contact(
                    name="Dra. Roberta Teste",
                    role="Advogada Titular",
                    phone="(21) 99999-8888",
                )
            ],
            outreach=Outreach(
                opening_message="Bom dia, Roberta! Tudo bem?",
                human_review=True,
            ),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        cls.db.save_lead(cls.test_lead)

        # Start server in daemon thread
        cls.port = 8899
        cls.host = "127.0.0.1"
        cls.server = ThreadingHTTPServer((cls.host, cls.port), CRMRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://{cls.host}:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        CRMRequestHandler.db_override = None
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _get(self, path: str):
        req = Request(f"{self.base_url}{path}")
        with urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: dict):
        data_bytes = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_serve_index_html(self):
        """Verifies that the server serves the SPA HTML."""
        req = Request(f"{self.base_url}/")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            html = resp.read().decode("utf-8")
            self.assertIn("Wake Prospector CRM", html)
            self.assertIn("Kanban", html)

    def test_get_stats(self):
        """Verifies that /api/stats returns funnel metrics."""
        status, data = self._get("/api/stats")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["success"])
        stats = data["stats"]
        self.assertIn("total", stats)
        self.assertIn("ready_for_review", stats)
        self.assertIn("discarded", stats)
        self.assertGreater(stats["total"], 0)

    def test_get_leads(self):
        """Verifies that /api/leads returns enriched lead objects."""
        status, data = self._get("/api/leads")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["success"])
        self.assertGreater(data["total"], 0)

        # Check enrichment
        sample = data["leads"][0]
        self.assertIn("enriched", sample)
        self.assertIn("wa_link", sample["enriched"])
        self.assertIn("is_seen", sample["enriched"])

    def test_mark_seen(self):
        """Verifies toggling seen state."""
        lead_id = self.test_lead.id
        status, data = self._post(f"/api/leads/{lead_id}/mark-seen", {"is_seen": True})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["is_seen"])

        # Fetch and check in GET
        status, get_data = self._get(f"/api/leads/{lead_id}")
        self.assertTrue(get_data["lead"]["metadata"]["is_seen"])

    def test_confirm_sent_and_record_response_lifecycle(self):
        """Verifies manual WhatsApp confirmation and subsequent response registration."""
        lead_id = self.test_lead.id

        # 1. Confirm sent
        status, sent_data = self._post(
            f"/api/leads/{lead_id}/confirm-sent",
            {"notes": "Teste de envio pelo CRM"},
        )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(sent_data["success"])
        self.assertEqual(sent_data["lead"]["pipeline_status"], PipelineStatus.WAITING_REPLY.value)

        # 2. Record incoming response with interest
        status, resp_data = self._post(
            f"/api/leads/{lead_id}/record-response",
            {
                "text": "Olá! Gostaria de saber mais sobre a proposta de vocês, podemos conversar?",
                "intent": "INTERESTED",
            },
        )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(resp_data["success"])
        self.assertEqual(resp_data["intent"], "INTERESTED")
        self.assertEqual(resp_data["status"], PipelineStatus.INTERESTED_HANDOFF.value)
        self.assertIsNotNone(resp_data["handoff_dossier"])

    def test_discard_lead_with_reason(self):
        """Verifies lead discard endpoint with mandatory reason."""
        # Create a disposable lead for discard test
        disposable = Lead(
            business=Business(
                name="Advogado Descarte Teste",
                city="Rio de Janeiro",
                neighborhood="Barra da Tijuca",
            ),
            pipeline_status=PipelineStatus.READY_FOR_REVIEW,
        )
        self.db.save_lead(disposable)

        # 1. Reject without reason
        try:
            self._post(f"/api/leads/{disposable.id}/discard", {"reason": ""})
            self.fail("Should have failed without reason")
        except HTTPError as e:
            self.assertEqual(e.code, HTTPStatus.BAD_REQUEST)

        # 2. Discard with valid reason
        status, data = self._post(
            f"/api/leads/{disposable.id}/discard",
            {"reason": "Já possui website institucional próprio confirmado"},
        )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["success"])
        self.assertEqual(data["lead"]["pipeline_status"], PipelineStatus.DISCARDED.value)


if __name__ == "__main__":
    unittest.main()
