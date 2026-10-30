"""Lightweight, zero-cost HTTP server and REST API for Wake Prospector CRM.

Operates purely with the Python standard library (http.server, json, sqlite3).
Provides REST endpoints and serves the modern SPA web application.
"""

import json
import mimetypes
import os
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.audit import AdversarialAuditService
from src.config import DATA_DIR, PipelineStatus, ResponseIntent
from src.conversation import ConversationService
from src.database import DatabaseManager
from src.deduplication import format_display_phone, normalize_phone
from src.logger import get_logger, log_event
from src.models import Lead
from src.qualification import (
    build_clinic_fallback_outreach,
    build_professional_outreach,
)
from src.review import ReviewService

logger = get_logger()

WEB_DIR = Path(WORKSPACE_ROOT) / "web"


class CRMRequestHandler(BaseHTTPRequestHandler):
    """Handles REST API requests and serves static CRM frontend."""
    db_override: Optional[DatabaseManager] = None

    def __init__(self, *args, **kwargs):
        self.db = CRMRequestHandler.db_override or DatabaseManager()
        self.conversation_svc = ConversationService(db=self.db)
        self.review_svc = ReviewService(db=self.db)
        self.audit_svc = AdversarialAuditService(db=self.db)
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppresses default stderr logging or routes to project logger."""
        pass

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        """Sends a JSON response with proper CORS and headers."""
        response_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        """Sends an error response in JSON format."""
        self._send_json({"success": False, "error": message}, status=status)

    def do_OPTIONS(self) -> None:
        """Handles CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handles GET requests for static files and REST API."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # REST API Routes
        if path == "/api/leads":
            self._handle_get_leads(parsed_url.query)
            return

        if path == "/api/stats":
            self._handle_get_stats()
            return

        if path == "/api/audit":
            self._handle_get_audit()
            return

        match_lead = re.match(r"^/api/leads/([^/]+)$", path)
        if match_lead:
            lead_id = match_lead.group(1)
            self._handle_get_lead(lead_id)
            return

        # Static File Serving (SPA)
        if path in ("", "/", "/index.html"):
            self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return

        # Serve static assets under web/
        requested_file = (WEB_DIR / path.lstrip("/")).resolve()
        # Security check: ensure path remains inside WEB_DIR
        if WEB_DIR in requested_file.parents and requested_file.is_file():
            mime_type, _ = mimetypes.guess_type(str(requested_file))
            self._serve_file(requested_file, mime_type or "application/octet-stream")
            return

        self._send_error("Recurso não encontrado", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Handles POST requests for state mutations."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                if raw_body.strip():
                    body = json.loads(raw_body)
            except Exception as e:
                self._send_error(f"JSON inválido no corpo da requisição: {e}")
                return

        # Routes: /api/leads/<id>/confirm-sent
        match_confirm = re.match(r"^/api/leads/([^/]+)/confirm-sent$", path)
        if match_confirm:
            lead_id = match_confirm.group(1)
            self._handle_confirm_sent(lead_id, body)
            return

        # Routes: /api/leads/<id>/discard
        match_discard = re.match(r"^/api/leads/([^/]+)/discard$", path)
        if match_discard:
            lead_id = match_discard.group(1)
            self._handle_discard(lead_id, body)
            return

        # Routes: /api/leads/<id>/record-response
        match_response = re.match(r"^/api/leads/([^/]+)/record-response$", path)
        if match_response:
            lead_id = match_response.group(1)
            self._handle_record_response(lead_id, body)
            return

        # Routes: /api/leads/<id>/mark-seen
        match_seen = re.match(r"^/api/leads/([^/]+)/mark-seen$", path)
        if match_seen:
            lead_id = match_seen.group(1)
            self._handle_mark_seen(lead_id, body)
            return

        self._send_error("Endpoint não encontrado", HTTPStatus.NOT_FOUND)

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        """Serves a static file from disk."""
        if not file_path.exists():
            self._send_error("Arquivo estático não encontrado", HTTPStatus.NOT_FOUND)
            return
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(f"Erro ao ler arquivo: {e}", HTTPStatus.INTERNAL_SERVER_ERROR)

    # -------------------------------------------------------------------------
    # API Handlers
    # -------------------------------------------------------------------------

    def _handle_get_leads(self, query_string: str) -> None:
        """Returns all leads with optional status filter."""
        params = parse_qs(query_string)
        status_filter = params.get("status", [None])[0]

        target_status = None
        if status_filter:
            try:
                target_status = PipelineStatus(status_filter.upper())
            except ValueError:
                self._send_error(f"Status inválido: {status_filter}")
                return

        leads = self.db.list_leads(pipeline_status=target_status)
        results = []

        for lead in leads:
            lead_dict = lead.to_dict()

            # Enrich with WhatsApp link & phone details (Primary = Owner Personal, Secondary = Clinic Fallback)
            target_contact = None
            for c in lead.contacts:
                if c.id == lead.outreach.recommended_contact_id:
                    target_contact = c
                    break
            if not target_contact and lead.contacts:
                target_contact = lead.contacts[0]

            clinic_contact = None
            for c in lead.contacts:
                if target_contact and c.id != target_contact.id:
                    clinic_contact = c
                    break

            phone_norm = ""
            wa_link = ""
            contact_name = ""
            contact_role = ""
            contact_type = ""
            if target_contact:
                contact_name = target_contact.name
                contact_role = target_contact.role
                contact_type = (
                    target_contact.type.value
                    if hasattr(target_contact.type, "value")
                    else str(target_contact.type)
                )
                if target_contact.phone:
                    phone_norm = normalize_phone(target_contact.phone)
                    live_owner_msg = build_professional_outreach(lead, target_contact)
                    lead_dict["outreach"]["opening_message"] = live_owner_msg
                    encoded_msg = quote(live_owner_msg)
                    wa_link = f"https://wa.me/{phone_norm}?text={encoded_msg}"

            display_phone = (
                format_display_phone(target_contact.phone)
                if (target_contact and target_contact.phone)
                else ""
            )

            clinic_phone_norm = ""
            clinic_display_phone = ""
            clinic_wa_link = ""
            clinic_role = "Recepção / Atendimento da Clínica (Fallback)"
            clinic_msg = build_clinic_fallback_outreach(lead, target_contact)
            raw_clinic_phone = (
                clinic_contact.phone
                if (clinic_contact and clinic_contact.phone)
                else lead_dict.get("metadata", {}).get("clinic_phone", "")
            )
            if clinic_contact and clinic_contact.role:
                clinic_role = clinic_contact.role
            if raw_clinic_phone:
                clinic_phone_norm = normalize_phone(raw_clinic_phone)
                clinic_display_phone = format_display_phone(raw_clinic_phone)
                encoded_clinic_msg = quote(clinic_msg)
                clinic_wa_link = f"https://wa.me/{clinic_phone_norm}?text={encoded_clinic_msg}"

            lead_dict["enriched"] = {
                "contact_name": contact_name,
                "contact_role": contact_role,
                "contact_type": contact_type,
                "normalized_phone": phone_norm,
                "display_phone": display_phone,
                "wa_link": wa_link,
                "clinic_display_phone": clinic_display_phone,
                "clinic_normalized_phone": clinic_phone_norm,
                "clinic_role": clinic_role,
                "clinic_wa_link": clinic_wa_link,
                "clinic_message": clinic_msg,
                "is_seen": lead_dict.get("metadata", {}).get("is_seen", False),
                "audit": lead_dict.get("metadata", {}).get("audit", {}),
            }
            results.append(lead_dict)

        self._send_json({"success": True, "total": len(results), "leads": results})

    def _handle_get_audit(self) -> None:
        """Returns batch adversarial audit summary across all active leads."""
        summary = self.audit_svc.audit_all_leads(only_active=True, require_audit_dossier=True)
        self._send_json({"success": True, "audit": summary})

    def _handle_get_stats(self) -> None:
        """Returns aggregated funnel statistics."""
        all_leads = self.db.list_leads()
        stats = {
            "total": len(all_leads),
            "ready_for_review": 0,
            "contacted": 0,
            "waiting_reply": 0,
            "responded": 0,
            "interested_handoff": 0,
            "discarded": 0,
            "strong": 0,
            "possible": 0,
            "seen": 0,
        }

        for l in all_leads:
            st = l.pipeline_status
            if st == PipelineStatus.READY_FOR_REVIEW:
                stats["ready_for_review"] += 1
            elif st == PipelineStatus.CONTACTED:
                stats["contacted"] += 1
            elif st == PipelineStatus.WAITING_REPLY:
                stats["waiting_reply"] += 1
            elif st == PipelineStatus.RESPONDED:
                stats["responded"] += 1
            elif st == PipelineStatus.INTERESTED_HANDOFF:
                stats["interested_handoff"] += 1
            elif st == PipelineStatus.DISCARDED:
                stats["discarded"] += 1

            cls_val = (
                l.opportunity.classification.value
                if hasattr(l.opportunity.classification, "value")
                else str(l.opportunity.classification)
            )
            if cls_val == "STRONG":
                stats["strong"] += 1
            elif cls_val == "POSSIBLE":
                stats["possible"] += 1

            if l.metadata.get("is_seen", False):
                stats["seen"] += 1

        self._send_json({"success": True, "stats": stats})

    def _handle_get_lead(self, lead_id: str) -> None:
        """Returns details for a single lead."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            self._send_error(f"Lead {lead_id} não encontrado", HTTPStatus.NOT_FOUND)
            return
        self._send_json({"success": True, "lead": lead.to_dict()})

    def _handle_confirm_sent(self, lead_id: str, body: Dict[str, Any]) -> None:
        """Confirms that manual WhatsApp outreach was performed."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            self._send_error(f"Lead {lead_id} não encontrado", HTTPStatus.NOT_FOUND)
            return

        message = body.get("message") or lead.outreach.opening_message
        notes = body.get("notes") or "Envio manual confirmado via CRM Web"

        try:
            lead = self.conversation_svc.confirm_manual_send(
                lead_id=lead_id, sent_message=message, notes=notes
            )
            lead.metadata["is_seen"] = True
            self.db.save_lead(lead)
            self._send_json(
                {
                    "success": True,
                    "message": f"Envio confirmado para [{lead.business.name}]",
                    "lead": lead.to_dict(),
                }
            )
        except Exception as e:
            self._send_error(f"Falha ao confirmar envio: {e}")

    def _handle_discard(self, lead_id: str, body: Dict[str, Any]) -> None:
        """Discards a lead with mandatory explanation reason."""
        reason = body.get("reason", "").strip()
        if not reason:
            self._send_error("Motivo do descarte é obrigatório (Regra D002 / Spec)")
            return

        lead = self.db.get_lead(lead_id)
        if not lead:
            self._send_error(f"Lead {lead_id} não encontrado", HTTPStatus.NOT_FOUND)
            return

        try:
            lead = self.db.update_lead_status(
                lead_id=lead_id,
                new_status=PipelineStatus.DISCARDED,
                reason=reason,
            )
            self._send_json(
                {
                    "success": True,
                    "message": f"Lead [{lead.business.name}] descartado com sucesso",
                    "lead": lead.to_dict(),
                }
            )
        except Exception as e:
            self._send_error(f"Falha ao descartar lead: {e}")

    def _handle_record_response(self, lead_id: str, body: Dict[str, Any]) -> None:
        """Records client response and determines intent."""
        text = body.get("text", "").strip()
        if not text:
            self._send_error("Texto da resposta é obrigatório")
            return

        intent_override = None
        raw_intent = body.get("intent")
        if raw_intent:
            try:
                intent_override = ResponseIntent(raw_intent)
            except ValueError:
                pass

        notes = body.get("notes")
        try:
            lead, conv, handoff = self.conversation_svc.process_inbound_response(
                lead_id=lead_id,
                text=text,
                intent_override=intent_override,
                notes=notes,
            )
            self._send_json(
                {
                    "success": True,
                    "intent": conv.intent.value,
                    "status": lead.pipeline_status.value,
                    "handoff_dossier": handoff,
                    "lead": lead.to_dict(),
                }
            )
        except Exception as e:
            self._send_error(f"Falha ao registrar resposta: {e}")

    def _handle_mark_seen(self, lead_id: str, body: Dict[str, Any]) -> None:
        """Toggles or sets the seen flag on a lead."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            self._send_error(f"Lead {lead_id} não encontrado", HTTPStatus.NOT_FOUND)
            return

        is_seen = body.get("is_seen", True)
        lead.metadata["is_seen"] = bool(is_seen)
        self.db.save_lead(lead)
        self._send_json(
            {"success": True, "lead_id": lead.id, "is_seen": lead.metadata["is_seen"]}
        )


def run_server(port: int = 8000, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Starts the CRM HTTP server."""
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), CRMRequestHandler)
    print("=" * 70)
    print(f"[+] WAKE PROSPECTOR CRM RODANDO EM: http://{host}:{port}")
    print("=" * 70)
    print("Pressione Ctrl+C para encerrar o servidor.")
    return server


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Wake Prospector CRM Server")
    parser.add_argument("--port", type=int, default=8000, help="Porta HTTP (padrão: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host (padrão: 127.0.0.1)")
    args = parser.parse_args()

    httpd = run_server(port=args.port, host=args.host)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor CRM...")
        httpd.server_close()
