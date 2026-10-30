"""Executable audit script for the 'adversarial-lead-audit' workspace skill."""

import json
import os
import sys

WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.audit import AdversarialAuditService
from src.database import DatabaseManager


def main() -> int:
    db = DatabaseManager()
    audit_svc = AdversarialAuditService(db=db)
    summary = audit_svc.audit_all_leads(only_active=True, require_audit_dossier=True)

    print("=" * 72)
    print("RELATÓRIO DE AUDITORIA CONTRADITÓRIA (ADVERSARIAL LEAD AUDIT)")
    print("=" * 72)
    print(f"Total Auditados      : {summary['total_audited']}")
    print(f"Aprovados (100% OK)  : {summary['passed']}")
    print(f"Reprovados / Alertas : {summary['failed']}")
    print(f"Colisões de Telefone : {summary['phone_collisions_count']}")
    print(f"Status Geral do Lote : {'APROVADO' if summary['all_passed'] else 'REPROVADO'}")
    print("-" * 72)

    for res in summary["results"]:
        status_icon = "[OK]" if res["passed"] else "[FALHA]"
        print(f"{status_icon} {res['business_name']} ({res['lead_id']}) — Tel: {res['phone_display']}")
        for err in res["errors"]:
            print(f"    ❌ ERRO: {err}")
        for warn in res["warnings"]:
            print(f"    ⚠️ AVISO: {warn}")

    print("=" * 72)
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
