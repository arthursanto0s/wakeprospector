"""Adversarial Lead Audit and Deep Verification Service for Wake Prospector.

Implements the 'adversarial-lead-audit' skill in code:
1. 1-to-1 Phone-to-Business Uniqueness Guard (zero phone collisions across leads).
2. Brazilian Phone Integrity & Anti-Synthetic Validation (detects fake sequential numbers
   and corrupted landlines with artificial '9' prefixes).
3. Public CNPJ/QSA Lookup via free BrasilAPI / ReceitaWS (zero-cost stdlib urllib).
4. Dialectical Adversarial Audit ('Advogado do Diabo'): records phone provenance,
   professional/decision-maker analysis, adversarial counter-arguments, and factual refutation.
5. Coherence verification between business name, responsible person, phone, and outreach message.
"""

from dataclasses import dataclass, field
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from src.config import PipelineStatus, WebsiteStatus
from src.database import DatabaseManager
from src.deduplication import (
    extract_domain,
    format_display_phone,
    is_generic_domain,
    normalize_business_name,
    normalize_phone,
    parse_br_phone,
)
from src.logger import get_logger, log_event
from src.models import Lead, utc_now_iso
from src.qualification import (
    clean_spoken_company_name,
    extract_first_name,
    is_individual_person,
)

logger = get_logger()

# Sequential patterns that indicate fabricated/placeholder phone numbers
SEQUENTIAL_SUBSCRIBER_PATTERNS = (
    "1234567",
    "2345678",
    "3456789",
    "4567890",
    "9876543",
    "8765432",
    "7654321",
    "6543210",
    "0123456",
)


def is_synthetic_or_corrupted_phone(raw_phone: str) -> Tuple[bool, str]:
    """Detects synthetic/sequential phone numbers or landlines with an artificial '9' added."""
    parsed = parse_br_phone(raw_phone)
    norm = parsed.get("normalized", "")
    if not norm or len(norm) < 12:
        return True, f"Telefone inválido ou incompleto: '{raw_phone}'"

    national = norm[2:] if norm.startswith("55") else norm

    # Check if someone prepended '9' to a landline (in Brazil, after DDD + 9, the next digit
    # for mobile numbers is [6-9], whereas [2-5] indicates a fixed landline that got a fake '9')
    if len(national) == 11 and national[2] == "9" and national[3] in "2345":
        return (
            True,
            f"Telefone fixo corrompido com dígito '9' artificial: '{raw_phone}' (4º dígito nacional '{national[3]}' é de linha fixa)",
        )

    subscriber = national[2:]
    for seq in SEQUENTIAL_SUBSCRIBER_PATTERNS:
        if seq in subscriber:
            return (
                True,
                f"Padrão numérico sequencial/sintético detectado ({seq}) no telefone '{raw_phone}'",
            )

    # Check if all 8 last digits are identical (e.g. 9999-9999)
    last8 = subscriber[-8:]
    if len(set(last8)) == 1:
        return (
            True,
            f"Padrão numérico repetitivo/sintético detectado ({last8}) no telefone '{raw_phone}'",
        )

    return False, ""


@dataclass
class LeadAuditResult:
    lead_id: str
    business_name: str
    passed: bool
    phone_normalized: str = ""
    phone_display: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    audit_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "business_name": self.business_name,
            "passed": self.passed,
            "phone_normalized": self.phone_normalized,
            "phone_display": self.phone_display,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "audit_metadata": dict(self.audit_metadata),
        }


class AdversarialAuditService:
    """Performs deep verification and dialectical adversarial audit on leads."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    @staticmethod
    def fetch_cnpj_public_data(cnpj: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
        """Queries free public BrasilAPI (with ReceitaWS fallback) for CNPJ & QSA data."""
        clean_cnpj = re.sub(r"\D", "", cnpj or "")
        if len(clean_cnpj) != 14:
            return None

        urls = [
            f"https://brasilapi.com.br/api/cnpj/v1/{clean_cnpj}",
            f"https://receitaws.com.br/v1/cnpj/{clean_cnpj}",
        ]
        headers = {
            "User-Agent": "WakeProspectorAudit/1.0 (Internal Commercial Intelligence)"
        }
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if isinstance(data, dict) and data.get("status") != "ERROR":
                            return data
            except Exception:
                continue
        return None

    def attach_adversarial_audit(
        self,
        lead_id: str,
        phone_provenance: str,
        decision_maker_analysis: str,
        adversarial_challenge: str,
        adversarial_verdict: str,
        verified_sources: Optional[List[str]] = None,
    ) -> Lead:
        """Records the dialectical adversarial audit dossier on a lead's metadata."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        if not phone_provenance.strip():
            raise ValueError("phone_provenance (Auditoria de vínculo do número) é obrigatório.")
        if not adversarial_challenge.strip():
            raise ValueError("adversarial_challenge (Contestação / Advogado do Diabo) é obrigatório.")
        if not adversarial_verdict.strip():
            raise ValueError("adversarial_verdict (Veredito Comprobatório) é obrigatório.")

        audit_record = {
            "phone_provenance": phone_provenance.strip(),
            "decision_maker_analysis": decision_maker_analysis.strip(),
            "adversarial_challenge": adversarial_challenge.strip(),
            "adversarial_verdict": adversarial_verdict.strip(),
            "verified_sources": list(verified_sources or [s.url for s in lead.sources if s.url]),
            "audited_at": utc_now_iso(),
            "audit_status": "VERIFIED",
        }
        lead.metadata["audit"] = audit_record
        lead = self.db.save_lead(lead)

        entry = log_event(
            event_type="ADVERSARIAL_AUDIT_ATTACHED",
            lead_id=lead.id,
            details={
                "business_name": lead.business.name,
                "phone_provenance": audit_record["phone_provenance"],
                "audit_status": "VERIFIED",
            },
        )
        self.db.insert_audit_log(entry)
        return lead

    def audit_single_lead(
        self,
        lead: Lead,
        phone_owners_map: Optional[Dict[str, List[Tuple[str, str]]]] = None,
        require_audit_dossier: bool = True,
    ) -> LeadAuditResult:
        """Runs comprehensive deterministic + adversarial checks on a single lead."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Business Name & Location check
        if not lead.business.name or len(lead.business.name.strip()) < 3:
            errors.append("Nome da empresa ausente ou inválido.")
        if not lead.business.neighborhood or not lead.business.address:
            warnings.append("Endereço ou bairro não detalhado completamente.")

        # 2. Website Status Check (V1 Rule D002)
        if lead.pipeline_status != PipelineStatus.DISCARDED:
            if lead.business.website_status == WebsiteStatus.WEBSITE_FOUND:
                errors.append(
                    f"Lead ativo possui website próprio ({lead.business.website}) e deveria estar DISCARDED (Regra D002)."
                )
            elif lead.business.website:
                domain = extract_domain(lead.business.website)
                if domain and not is_generic_domain(domain):
                    errors.append(
                        f"Campo website preenchido com domínio próprio ({domain}) em lead não descartado."
                    )

        # 3. Contact & Phone Verification
        target_contact = None
        for c in lead.contacts:
            if c.id == lead.outreach.recommended_contact_id:
                target_contact = c
                break
        if not target_contact and lead.contacts:
            target_contact = lead.contacts[0]

        norm_phone = ""
        disp_phone = ""
        if not target_contact or not target_contact.phone:
            errors.append("Nenhum telefone de contato registrado para o lead.")
        else:
            raw_phone = target_contact.phone
            norm_phone = normalize_phone(raw_phone)
            disp_phone = format_display_phone(raw_phone)

            is_bad, bad_reason = is_synthetic_or_corrupted_phone(raw_phone)
            if is_bad:
                errors.append(bad_reason)

            # Check 1-to-1 phone uniqueness across database
            if phone_owners_map and norm_phone:
                owners = phone_owners_map.get(norm_phone, [])
                other_owners = [
                    f"{bname} ({lid})" for lid, bname in owners if lid != lead.id
                ]
                if other_owners:
                    errors.append(
                        f"COLISÃO DE TELEFONE (1:1 VIOLADO): O número {disp_phone} está duplicado em outra(s) empresa(s): {', '.join(other_owners)}."
                    )

            # Check secondary (clinic fallback) contact if present
            for sec_c in lead.contacts:
                if sec_c.id != target_contact.id and sec_c.phone:
                    sec_norm = normalize_phone(sec_c.phone)
                    sec_disp = format_display_phone(sec_c.phone)
                    if sec_norm == norm_phone:
                        errors.append(
                            f"NÚMEROS IDÊNTICOS NO MESMO LEAD: O contato pessoal e o contato da clínica são iguais ({sec_disp})."
                        )
                    if phone_owners_map and sec_norm:
                        sec_owners = phone_owners_map.get(sec_norm, [])
                        sec_other = [
                            f"{bname} ({lid})" for lid, bname in sec_owners if lid != lead.id
                        ]
                        if sec_other:
                            errors.append(
                                f"COLISÃO DE TELEFONE SECUNDÁRIO (1:1 VIOLADO): O número da clínica {sec_disp} está duplicado em: {', '.join(sec_other)}."
                            )

        # 4. Outreach Message Coherence Check
        msg = lead.outreach.opening_message or ""
        if lead.pipeline_status == PipelineStatus.READY_FOR_REVIEW:
            if not msg:
                errors.append("Mensagem inicial (opening_message) está vazia.")
            else:
                msg_lower = msg.lower().strip()
                if not msg_lower.startswith(("bom dia", "boa tarde", "boa noite", "olá")):
                    errors.append(
                        f"Incoerência na saudação de horário: A mensagem ('{msg}') não inicia com Bom dia / Boa tarde / Boa noite."
                    )
                if target_contact and is_individual_person(target_contact.name, target_contact.role):
                    first_name = extract_first_name(target_contact.name)
                    if first_name and first_name.lower() not in msg_lower:
                        errors.append(
                            f"Incoerência na saudação: O responsável '{target_contact.name}' é pessoa física, mas seu primeiro nome ('{first_name}') não consta na mensagem ('{msg}')."
                        )
                    if "tudo bem?" not in msg_lower:
                        errors.append(
                            f"Incoerência na mensagem pessoal do doutor(a): Deve encerrar com 'tudo bem?' ('{msg}')."
                        )
                else:
                    spoken_name = clean_spoken_company_name(lead.business.name)
                    if spoken_name.lower() not in msg_lower:
                        errors.append(
                            f"Incoerência na mensagem institucional: O nome limpo da empresa ('{spoken_name}') não consta na mensagem ('{msg}')."
                        )

        # 5. Sources Check
        if not lead.sources:
            errors.append("Nenhuma fonte pública documentada para o lead.")

        # 6. Adversarial Audit Dossier Check
        audit_data = lead.metadata.get("audit", {})
        if require_audit_dossier and lead.pipeline_status == PipelineStatus.READY_FOR_REVIEW:
            if not audit_data:
                errors.append(
                    "Dossiê de Auditoria Contraditória ('metadata.audit') ausente."
                )
            else:
                if not audit_data.get("phone_provenance"):
                    errors.append("Auditoria sem 'phone_provenance' (justificativa do vínculo do número).")
                if not audit_data.get("adversarial_challenge"):
                    errors.append("Auditoria sem 'adversarial_challenge' (combate de argumentos / Advogado do Diabo).")
                if not audit_data.get("adversarial_verdict"):
                    errors.append("Auditoria sem 'adversarial_verdict' (veredito de refutação).")

        passed = len(errors) == 0
        return LeadAuditResult(
            lead_id=lead.id,
            business_name=lead.business.name,
            passed=passed,
            phone_normalized=norm_phone,
            phone_display=disp_phone,
            errors=errors,
            warnings=warnings,
            audit_metadata=audit_data,
        )

    def audit_all_leads(
        self,
        only_active: bool = True,
        require_audit_dossier: bool = True,
    ) -> Dict[str, Any]:
        """Audits all leads in the database, checking for cross-lead phone collisions and data integrity."""
        all_leads = self.db.list_leads()
        target_leads = [
            l
            for l in all_leads
            if not only_active or l.pipeline_status != PipelineStatus.DISCARDED
        ]

        # Build phone -> [(lead_id, business_name)] map across all active leads
        phone_owners_map: Dict[str, List[Tuple[str, str]]] = {}
        for l in target_leads:
            for c in l.contacts:
                if c.phone:
                    norm = normalize_phone(c.phone)
                    if norm:
                        phone_owners_map.setdefault(norm, [])
                        if (l.id, l.business.name) not in phone_owners_map[norm]:
                            phone_owners_map[norm].append((l.id, l.business.name))

        results: List[LeadAuditResult] = []
        passed_count = 0
        failed_count = 0

        for l in target_leads:
            res = self.audit_single_lead(
                l,
                phone_owners_map=phone_owners_map,
                require_audit_dossier=require_audit_dossier,
            )
            results.append(res)
            if res.passed:
                passed_count += 1
            else:
                failed_count += 1

        collisions = {
            phone: owners
            for phone, owners in phone_owners_map.items()
            if len(owners) > 1
        }

        summary = {
            "total_audited": len(target_leads),
            "passed": passed_count,
            "failed": failed_count,
            "phone_collisions_count": len(collisions),
            "all_passed": failed_count == 0 and len(collisions) == 0,
            "results": [r.to_dict() for r in results],
        }

        entry = log_event(
            event_type="BATCH_ADVERSARIAL_AUDIT_COMPLETED",
            details={
                "total_audited": len(target_leads),
                "passed": passed_count,
                "failed": failed_count,
                "phone_collisions_count": len(collisions),
            },
        )
        self.db.insert_audit_log(entry)
        return summary
