"""Review interface service for Wake Prospector (Phase 5).

Provides daily review queues, decision cards, and lightweight HTML exports
answering the 9 critical decision questions without bloated UI frameworks.
"""

from html import escape
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from src.config import DATA_DIR, OpportunityClass, PipelineStatus
from src.database import DatabaseManager
from src.deduplication import format_display_phone, normalize_phone
from src.models import Contact, Lead


OPPORTUNITY_ORDER = {
    OpportunityClass.STRONG: 1,
    OpportunityClass.POSSIBLE: 2,
    OpportunityClass.UNCERTAIN: 3,
    OpportunityClass.LOW_PRIORITY: 4,
}


class ReviewService:
    """Manages the daily review queue and operator decision cards."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def get_review_queue(self) -> List[Lead]:
        """Returns leads ready for human review, sorted with strongest evidence first."""
        leads = self.db.list_leads(pipeline_status=PipelineStatus.READY_FOR_REVIEW)

        def sort_key(lead: Lead) -> int:
            return OPPORTUNITY_ORDER.get(lead.opportunity.classification, 99)

        return sorted(leads, key=sort_key)

    def render_decision_card(self, lead: Lead) -> str:
        """Renders an executive decision card answering the 9 questions from docs/PROJECT_SPEC.md."""
        target_contact: Optional[Contact] = None
        for c in lead.contacts:
            if c.id == lead.outreach.recommended_contact_id:
                target_contact = c
                break
        if not target_contact and lead.contacts:
            target_contact = lead.contacts[0]

        lines = [
            "=" * 65,
            f"FICHA DE DECISÃO RÁPIDA: [{lead.id}]",
            "=" * 65,
            f"1. QUEM É?         : {lead.business.name} ({lead.business.category or 'Sem categoria'})",
            f"2. ONDE ESTÁ?      : {lead.business.city} - {lead.business.neighborhood or 'Bairro N/I'} | {lead.business.address or 'N/I'}",
            f"3. TEM SITE?       : {lead.business.website_status.value} ({lead.business.website or 'Nenhum site próprio'})",
        ]

        if target_contact and target_contact.name:
            lines.append(
                f"4. RESPONSÁVEL     : {target_contact.name} ({target_contact.role or 'Responsável'}) [Confiança: {target_contact.confidence.value}]"
            )
        else:
            lines.append(
                "4. RESPONSÁVEL     : Não identificado com certeza (abordagem institucional)"
            )

        clinic_contact: Optional[Contact] = None
        for c in lead.contacts:
            if target_contact and c.id != target_contact.id:
                clinic_contact = c
                break

        if target_contact and target_contact.phone:
            lines.append(
                f"5. NÚMERO PESSOAL  : {format_display_phone(target_contact.phone)} [{target_contact.type.value}]"
            )
        else:
            lines.append("5. QUAL NÚMERO?    : Nenhum telefone registrado")

        if clinic_contact and clinic_contact.phone:
            lines.append(
                f"   NÚMERO CLÍNICA  : {format_display_phone(clinic_contact.phone)} [FALLBACK / RECEPÇÃO]"
            )

        lines.append(
            f"6. POR QUE ABORDAR?: [{lead.opportunity.classification.value}] {lead.opportunity.hypothesis or 'N/I'}"
        )
        if lead.opportunity.evidence:
            for ev in lead.opportunity.evidence:
                lines.append(f"     - Evidência: {ev}")

        if lead.opportunity.uncertainties:
            lines.append("7. INCERTEZAS      :")
            for unc in lead.opportunity.uncertainties:
                lines.append(f"     * {unc}")
        else:
            lines.append("7. INCERTEZAS      : Nenhuma incerteza crítica pendente")

        lines.append(f"8. FONTES ({len(lead.sources)})      :")
        for s in lead.sources:
            lines.append(f"     - [{s.source_type}] {s.title}: {s.url}")

        audit = lead.metadata.get("audit", {})
        if audit:
            lines.append("-" * 65)
            lines.append("AUDITORIA CONTRADITÓRIA & VÍNCULO DO NÚMERO (1:1):")
            if audit.get("phone_provenance"):
                lines.append(f"   * Vínculo do Número : {audit['phone_provenance']}")
            if audit.get("decision_maker_analysis"):
                lines.append(f"   * Análise Decisor   : {audit['decision_maker_analysis']}")
            if audit.get("adversarial_challenge"):
                lines.append(f"   * Contestação       : {audit['adversarial_challenge']}")
            if audit.get("adversarial_verdict"):
                lines.append(f"   * Veredito          : {audit['adversarial_verdict']}")

        lines.append("-" * 65)
        lines.append("9. MENSAGEM INICIAL SUGERIDA:")
        lines.append(f"   \"{lead.outreach.opening_message}\"")
        lines.append("=" * 65)
        return "\n".join(lines)

    def export_html_report(self, output_path: Optional[Path] = None) -> Path:
        """Generates a clean, standalone, zero-dependency HTML file to inspect the review queue."""
        queue = self.get_review_queue()
        out_file = output_path or (DATA_DIR / "leads" / "daily_review.html")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        cards_html = []
        for lead in queue:
            target_contact: Optional[Contact] = None
            for c in lead.contacts:
                if c.id == lead.outreach.recommended_contact_id:
                    target_contact = c
                    break
            if not target_contact and lead.contacts:
                target_contact = lead.contacts[0]

            phone_norm = (
                normalize_phone(target_contact.phone)
                if target_contact and target_contact.phone
                else ""
            )
            encoded_msg = quote(lead.outreach.opening_message)
            wa_link = (
                f"https://wa.me/{phone_norm}?text={encoded_msg}"
                if phone_norm
                else "#"
            )

            badge_color = "#10b981"  # green for STRONG
            if lead.opportunity.classification == OpportunityClass.POSSIBLE:
                badge_color = "#3b82f6"  # blue
            elif lead.opportunity.classification == OpportunityClass.UNCERTAIN:
                badge_color = "#f59e0b"  # amber
            elif lead.opportunity.classification == OpportunityClass.LOW_PRIORITY:
                badge_color = "#6b7280"  # gray

            ev_items = "".join(
                f"<li>{escape(ev)}</li>" for ev in lead.opportunity.evidence
            )
            unc_items = "".join(
                f"<li>{escape(unc)}</li>"
                for unc in lead.opportunity.uncertainties
            )
            sources_items = "".join(
                f"<li><span class='src-tag'>{escape(s.source_type)}</span> <a href='{escape(s.url)}' target='_blank'>{escape(s.title or s.url)}</a></li>"
                for s in lead.sources
            )

            resp_text = (
                f"{escape(target_contact.name)} ({escape(target_contact.role or 'Responsável')}) - Confiança: {escape(target_contact.confidence.value)}"
                if target_contact and target_contact.name
                else "Não identificado (Abordagem institucional)"
            )
            clinic_contact: Optional[Contact] = None
            for c in lead.contacts:
                if target_contact and c.id != target_contact.id:
                    clinic_contact = c
                    break

            phone_text = (
                f"{escape(format_display_phone(target_contact.phone))} ({escape(target_contact.type.value)})"
                if target_contact and target_contact.phone
                else "Sem telefone"
            )
            clinic_phone_text = (
                f"<p><strong>Telefone Clínica (Fallback):</strong> {escape(format_display_phone(clinic_contact.phone))} (RECEPÇÃO / CLÍNICA)</p>"
                if clinic_contact and clinic_contact.phone
                else ""
            )

            audit = lead.metadata.get("audit", {})
            audit_html = ""
            if audit:
                audit_html = f"""
                    <div class="section-box" style="border-left: 4px solid #10b981;">
                        <strong>🛡️ Auditoria Contraditória &amp; Vínculo 1:1 do Número:</strong>
                        <p><strong>Por que é este número:</strong> {escape(audit.get('phone_provenance', ''))}</p>
                        {f"<p><strong>Análise do Decisor:</strong> {escape(audit.get('decision_maker_analysis', ''))}</p>" if audit.get('decision_maker_analysis') else ""}
                        <p><strong>Contestação (Advogado do Diabo):</strong> {escape(audit.get('adversarial_challenge', ''))}</p>
                        <p><strong>Veredito Comprobatório:</strong> {escape(audit.get('adversarial_verdict', ''))}</p>
                    </div>
                """

            cards_html.append(
                f"""
            <div class="card">
                <div class="card-header">
                    <div>
                        <h2>{escape(lead.business.name)}</h2>
                        <span class="sub">{escape(lead.business.category or 'Comércio')} &bull; {escape(lead.business.city)} ({escape(lead.business.neighborhood or 'N/I')})</span>
                    </div>
                    <div>
                        <span class="badge" style="background-color: {badge_color};">{escape(lead.opportunity.classification.value)}</span>
                    </div>
                </div>
                <div class="card-body">
                    <p><strong>Responsável:</strong> {resp_text}</p>
                    <p><strong>Telefone Pessoal (Doutor/Sócio):</strong> {phone_text}</p>
                    {clinic_phone_text}
                    <p><strong>Site:</strong> {escape(lead.business.website_status.value)}</p>
                    
                    <div class="section-box">
                        <strong>Hipótese de Oportunidade:</strong>
                        <p>{escape(lead.opportunity.hypothesis or 'Nenhuma hipótese registrada.')}</p>
                        <strong>Evidências:</strong>
                        <ul>{ev_items or '<li>Nenhuma evidência registrada</li>'}</ul>
                    </div>

                    {audit_html}

                    {f'<div class="section-box alert"><strong>Incertezas:</strong><ul>{unc_items}</ul></div>' if unc_items else ''}

                    <div class="section-box">
                        <strong>Mensagem Inicial Sugerida:</strong>
                        <div class="msg-box">"{escape(lead.outreach.opening_message)}"</div>
                        {f'<a href="{wa_link}" target="_blank" class="btn">Abrir WhatsApp e Enviar</a>' if phone_norm else '<span class="disabled-btn">Telefone Indisponível</span>'}
                    </div>

                    <details>
                        <summary>Fontes Consultadas ({len(lead.sources)})</summary>
                        <ul>{sources_items or '<li>Nenhuma fonte registrada</li>'}</ul>
                    </details>
                </div>
            </div>
            """
            )

        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wake Prospector — Fila de Revisão Diária</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        .header {{ max-width: 900px; margin: 0 auto 24px auto; border-bottom: 1px solid #334155; padding-bottom: 16px; }}
        .header h1 {{ margin: 0 0 8px 0; color: #38bdf8; }}
        .container {{ max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }}
        .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
        .card-header h2 {{ margin: 0; font-size: 1.25rem; color: #f1f5f9; }}
        .sub {{ font-size: 0.875rem; color: #94a3b8; }}
        .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; color: #fff; text-transform: uppercase; }}
        .section-box {{ background: #0f172a; border-radius: 8px; padding: 12px; margin: 12px 0; font-size: 0.9rem; }}
        .section-box.alert {{ border-left: 4px solid #f59e0b; }}
        .msg-box {{ font-style: italic; color: #bae6fd; margin: 8px 0; padding: 8px; background: #1e293b; border-radius: 4px; }}
        .btn {{ display: inline-block; background: #22c55e; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 0.875rem; margin-top: 6px; }}
        .btn:hover {{ background: #16a34a; }}
        .disabled-btn {{ display: inline-block; background: #475569; color: #94a3b8; padding: 8px 16px; border-radius: 6px; font-size: 0.875rem; }}
        .src-tag {{ font-size: 0.75rem; background: #334155; padding: 2px 6px; border-radius: 4px; font-weight: bold; }}
        a {{ color: #38bdf8; }}
        details {{ margin-top: 10px; font-size: 0.85rem; color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Wake Prospector — Fila de Revisão Diária</h1>
        <p>Total de leads qualificados prontos para abordagem humana: <strong>{len(queue)}</strong></p>
    </div>
    <div class="container">
        {"".join(cards_html) if cards_html else '<p>Nenhum lead aguardando revisão no momento.</p>'}
    </div>
</body>
</html>
"""
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return out_file
