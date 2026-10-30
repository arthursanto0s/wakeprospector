"""Command line interface (CLI) for Wake Prospector.

Provides deterministic inspection, status transitions, deduplication checks,
review queue presentation, and response handling for operators and the agent.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.audit import AdversarialAuditService
from src.config import (
    ConfidenceLevel,
    DB_PATH,
    OpportunityClass,
    PipelineStatus,
    ResponseIntent,
    SourceType,
    WebsiteStatus,
)
from src.conversation import ConversationService
from src.database import DatabaseManager
from src.deduplication import check_lead_duplicate
from src.models import Business, Contact, Lead, Source
from src.qualification import OpportunityService
from src.research import ResearchService
from src.responsible import ResponsibleService
from src.review import ReviewService


def format_lead_card(lead: Lead) -> str:
    """Renders a readable lead summary card as specified in docs/PROJECT_SPEC.md."""
    lines = [
        "=" * 60,
        f"FICHA DO LEAD: {lead.id}",
        "=" * 60,
        f"Empresa: {lead.business.name}",
        f"Categoria: {lead.business.category}",
        f"Localização: {lead.business.city} ({lead.business.neighborhood or 'Bairro N/I'})",
        f"Endereço: {lead.business.address or 'N/I'}",
        f"Site: {lead.business.website or 'Nenhum site próprio identificado'}",
        f"Status do Site: {lead.business.website_status.value if hasattr(lead.business.website_status, 'value') else lead.business.website_status}",
        f"Status do Pipeline: {lead.pipeline_status.value if hasattr(lead.pipeline_status, 'value') else lead.pipeline_status}",
    ]
    if lead.discard_reason:
        lines.append(f"Motivo do Descarte: {lead.discard_reason}")

    lines.append("-" * 60)
    lines.append("CONTATOS E RESPONSÁVEL:")
    if not lead.contacts:
        lines.append("  (Nenhum contato registrado)")
    else:
        for idx, c in enumerate(lead.contacts, 1):
            is_rec = " [RECOMENDADO]" if c.id == lead.outreach.recommended_contact_id else ""
            lines.append(
                f"  [{idx}] ID: {c.id}{is_rec} | Nome: {c.name or 'Não identificado'} | Cargo: {c.role or 'N/I'}"
            )
            lines.append(
                f"      Telefone: {c.phone or 'N/I'} | Tipo: {c.type} | Confiança: {c.confidence}"
            )
            if c.evidence_ids:
                lines.append(f"      Fontes: {', '.join(c.evidence_ids)}")

    lines.append("-" * 60)
    lines.append("PRESENÇA DIGITAL:")
    lines.append(f"  Instagram: {lead.digital_presence.instagram or 'N/I'}")
    lines.append(f"  Facebook: {lead.digital_presence.facebook or 'N/I'}")
    lines.append(f"  Google Maps: {lead.digital_presence.google_maps or 'N/I'}")

    lines.append("-" * 60)
    lines.append("ANÁLISE DE OPORTUNIDADE:")
    lines.append(
        f"  Classificação: {lead.opportunity.classification.value if hasattr(lead.opportunity.classification, 'value') else lead.opportunity.classification}"
    )
    lines.append(f"  Hipótese: {lead.opportunity.hypothesis or 'N/I'}")
    if lead.opportunity.evidence:
        lines.append("  Evidências observadas:")
        for ev in lead.opportunity.evidence:
            lines.append(f"    - {ev}")
    if lead.opportunity.uncertainties:
        lines.append("  Incertezas:")
        for unc in lead.opportunity.uncertainties:
            lines.append(f"    * {unc}")

    lines.append("-" * 60)
    lines.append("ABORDAGEM SUGERIDA:")
    lines.append(f"  Contato Recomendado ID: {lead.outreach.recommended_contact_id or 'N/I'}")
    lines.append(f"  Mensagem Inicial: \"{lead.outreach.opening_message}\"")
    lines.append(f"  Revisão Humana Obrigatória: {lead.outreach.human_review}")

    lines.append("-" * 60)
    lines.append(f"FONTES REGISTRADAS ({len(lead.sources)}):")
    for s in lead.sources:
        lines.append(f"  [{s.id}] ({s.source_type}) {s.title} -> {s.url}")
        if s.supports:
            lines.append(f"      Sustenta: {', '.join(s.supports)}")

    lines.append("=" * 60)
    return "\n".join(lines)


def main(args: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wake Prospector CLI - Ferramenta de Infraestrutura Determinística"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db
    subparsers.add_parser("init-db", help="Inicializa o banco de dados SQLite local")

    # list-leads
    list_p = subparsers.add_parser("list-leads", help="Lista leads cadastrados")
    list_p.add_argument("--status", choices=[s.value for s in PipelineStatus], help="Filtrar por status")
    list_p.add_argument("--city", help="Filtrar por cidade")
    list_p.add_argument("--category", help="Filtrar por categoria")

    # show-lead
    show_p = subparsers.add_parser("show-lead", help="Exibe a ficha completa de um lead")
    show_p.add_argument("lead_id", help="ID do lead (ex: LEAD-2026-XXXXXX)")

    # update-status
    update_p = subparsers.add_parser("update-status", help="Atualiza status de um lead no pipeline")
    update_p.add_argument("lead_id", help="ID do lead")
    update_p.add_argument("new_status", choices=[s.value for s in PipelineStatus], help="Novo status")
    update_p.add_argument("--reason", help="Motivo (obrigatório se DISCARDED)")
    update_p.add_argument("--user-confirmed", action="store_true", help="Confirmação de envio manual humano (obrigatório se CONTACTED)")

    # check-duplicate
    dup_p = subparsers.add_parser("check-duplicate", help="Verifica duplicidade de empresa antes de cadastrar")
    dup_p.add_argument("--name", required=True, help="Nome da empresa")
    dup_p.add_argument("--city", required=True, help="Cidade da empresa")
    dup_p.add_argument("--phone", help="Telefone (opcional)")

    # add-candidate
    cand_p = subparsers.add_parser("add-candidate", help="Adiciona candidato descoberto com checagem de duplicidade")
    cand_p.add_argument("--name", required=True, help="Nome da empresa")
    cand_p.add_argument("--city", required=True, help="Cidade")
    cand_p.add_argument("--category", default="", help="Categoria ou nicho")
    cand_p.add_argument("--neighborhood", default="", help="Bairro")
    cand_p.add_argument("--phone", help="Telefone encontrado")
    cand_p.add_argument("--source-url", default="", help="URL da fonte de descoberta")
    cand_p.add_argument("--source-title", default="Descoberta Inicial", help="Título da fonte")

    # verify-company
    vcomp_p = subparsers.add_parser("verify-company", help="Registra corroboração de identidade da empresa")
    vcomp_p.add_argument("lead_id", help="ID do lead")
    vcomp_p.add_argument("--source-url", required=True, help="URL da fonte comprobatória")
    vcomp_p.add_argument("--source-title", required=True, help="Título da fonte comprobatória")
    vcomp_p.add_argument("--source-type", choices=[s.value for s in SourceType], default="E2", help="Tipo de fonte (E1 a E4)")
    vcomp_p.add_argument("--address", help="Endereço confirmado")
    vcomp_p.add_argument("--neighborhood", help="Bairro confirmado")

    # verify-website
    vweb_p = subparsers.add_parser("verify-website", help="Registra resultado da verificação de website")
    vweb_p.add_argument("lead_id", help="ID do lead")
    vweb_p.add_argument("--status", required=True, choices=[s.value for s in WebsiteStatus], help="Status do site")
    vweb_p.add_argument("--url", default="", help="URL do site encontrado (se houver)")
    vweb_p.add_argument("--notes", help="Notas ou incertezas observadas")

    # add-responsible
    resp_p = subparsers.add_parser("add-responsible", help="Adiciona responsável identificado com prova de vínculo")
    resp_p.add_argument("lead_id", help="ID do lead")
    resp_p.add_argument("--name", required=True, help="Nome completo do responsável")
    resp_p.add_argument("--role", required=True, help="Cargo ou relação (ex: Proprietário, Sócio, Administrador)")
    resp_p.add_argument("--source-url", required=True, help="URL da fonte que comprova o vínculo")
    resp_p.add_argument("--source-title", required=True, help="Título da fonte comprobatória")
    resp_p.add_argument("--source-type", choices=[s.value for s in SourceType], default="E1", help="Tipo de fonte (E1 a E4)")
    resp_p.add_argument("--proof", required=True, help="Descrição da evidência que liga a pessoa à empresa")
    resp_p.add_argument("--confidence", choices=[c.value for c in ConfidenceLevel], default="HIGH", help="Nível de confiança")

    # associate-phone
    assoc_p = subparsers.add_parser("associate-phone", help="Associa telefone a contato do lead com validação relacional")
    assoc_p.add_argument("lead_id", help="ID do lead")
    assoc_p.add_argument("--phone", required=True, help="Número de telefone a associar")
    assoc_p.add_argument("--contact-id", default="", help="ID do contato (ou vazio para o responsável principal)")
    assoc_p.add_argument("--is-person-associated", action="store_true", help="Marque apenas se o telefone tiver vínculo direto confirmado com a pessoa (e não só com a empresa)")
    assoc_p.add_argument("--source-url", default="", help="URL da fonte do telefone")
    assoc_p.add_argument("--source-title", default="Fonte de Telefone", help="Título da fonte")

    # select-contact
    sel_p = subparsers.add_parser("select-contact", help="Seleciona o melhor contato para a abordagem")
    sel_p.add_argument("lead_id", help="ID do lead")

    # qualify-lead
    qual_p = subparsers.add_parser("qualify-lead", help="Qualifica lead com evidências explicáveis e hipótese de utilidade")
    qual_p.add_argument("lead_id", help="ID do lead")
    qual_p.add_argument("--evidence", action="append", default=[], help="Evidência observada (pode ser repetida: --evidence E1 --evidence E2)")
    qual_p.add_argument("--hypothesis", default="", help="Hipótese factual de utilidade de um site próprio")
    qual_p.add_argument("--uncertainty", action="append", default=[], help="Incerteza observada (pode ser repetida)")
    qual_p.add_argument("--classification", choices=[c.value for c in OpportunityClass], help="Classificação explícita (STRONG, POSSIBLE, UNCERTAIN, LOW_PRIORITY)")

    # prepare-outreach
    out_p = subparsers.add_parser("prepare-outreach", help="Gera mensagem de abordagem inicial personalizada e move para READY_FOR_REVIEW")
    out_p.add_argument("lead_id", help="ID do lead")

    # daily-review
    subparsers.add_parser("daily-review", help="Exibe fila diária de leads prontos para revisão humana e decisão de abordagem")

    # confirm-sent
    sent_p = subparsers.add_parser("confirm-sent", help="Confirma o envio manual do WhatsApp para um lead (move para CONTACTED -> WAITING_REPLY)")
    sent_p.add_argument("lead_id", help="ID do lead contatado")
    sent_p.add_argument("--message", help="Mensagem enviada (opcional, padrão usa a mensagem sugerida)")
    sent_p.add_argument("--notes", default="", help="Notas adicionais sobre o envio")

    # record-response
    resp_in_p = subparsers.add_parser("record-response", help="Registra resposta recebida do prospect, classifica intenção e aciona handoff se interessado")
    resp_in_p.add_argument("lead_id", help="ID do lead")
    resp_in_p.add_argument("--text", required=True, help="Texto exato da resposta recebida")
    resp_in_p.add_argument("--intent", choices=[i.value for i in ResponseIntent], help="Sobrescrever classificação de intenção (opcional)")
    resp_in_p.add_argument("--notes", default="", help="Notas contextuais")

    # export-review-html
    html_p = subparsers.add_parser("export-review-html", help="Exporta a fila diária de revisão para uma página HTML visual")
    html_p.add_argument("--out", help="Caminho do arquivo HTML de destino")

    # log-query
    lq_p = subparsers.add_parser("log-query", help="Registra consulta de busca efetuada para auditoria")
    lq_p.add_argument("--query", required=True, help="Termo de pesquisa utilizado")
    lq_p.add_argument("--purpose", required=True, help="Objetivo da consulta")
    lq_p.add_argument("--lead-id", help="ID do lead associado (se houver)")

    # export-json
    export_p = subparsers.add_parser("export-json", help="Exporta todos os leads em formato JSON")
    export_p.add_argument("--out", help="Arquivo de destino (opcional, padrão imprime na tela)")

    # serve
    serve_p = subparsers.add_parser("serve", help="Inicia o servidor web CRM local para gestão interativa em tempo real")
    serve_p.add_argument("--port", type=int, default=8000, help="Porta HTTP (padrão: 8000)")
    serve_p.add_argument("--host", default="127.0.0.1", help="Host (padrão: 127.0.0.1)")

    # audit-leads
    subparsers.add_parser("audit-leads", help="Executa auditoria contraditória e checagem 1:1 de telefones em todos os leads ativos")

    parsed = parser.parse_args(args)
    db = DatabaseManager()
    research = ResearchService(db=db)
    responsible = ResponsibleService(db=db)
    opportunity = OpportunityService(db=db)
    review = ReviewService(db=db)
    conversation = ConversationService(db=db)

    if parsed.command == "init-db":
        db.init_db()
        print(f"Banco de dados inicializado com sucesso em: {DB_PATH}")
        return 0

    elif parsed.command == "list-leads":
        status_filter = PipelineStatus(parsed.status) if parsed.status else None
        leads = db.list_leads(pipeline_status=status_filter, city=parsed.city, category=parsed.category)
        print(f"Total de leads encontrados: {len(leads)}")
        for l in leads:
            st = l.pipeline_status.value if hasattr(l.pipeline_status, "value") else l.pipeline_status
            print(f"- [{l.id}] {l.business.name} | {l.business.city} | Status: {st}")
        return 0

    elif parsed.command == "show-lead":
        lead = db.get_lead(parsed.lead_id)
        if not lead:
            print(f"Erro: Lead com ID '{parsed.lead_id}' não foi encontrado.", file=sys.stderr)
            return 1
        print(format_lead_card(lead))
        return 0

    elif parsed.command == "update-status":
        try:
            lead = db.update_lead_status(
                lead_id=parsed.lead_id,
                new_status=PipelineStatus(parsed.new_status),
                reason=parsed.reason,
                user_confirmed=parsed.user_confirmed,
            )
            print(f"Status do lead {lead.id} atualizado para: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro na transição: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "check-duplicate":
        candidate = Lead(
            business=Business(name=parsed.name, city=parsed.city),
            contacts=[Contact(phone=parsed.phone)] if parsed.phone else [],
        )
        existing = db.list_leads()
        res = check_lead_duplicate(candidate, existing)
        if res.is_duplicate:
            print("ALERTA: Possível duplicata detectada!")
            print(f"Lead existente: {res.matched_lead_id}")
            print(f"Confiança: {res.confidence.value}")
            print(f"Critérios: {', '.join(res.matched_criteria)}")
            print(f"Motivo: {res.reason}")
        else:
            print("Nenhuma duplicata encontrada. O lead pode ser pesquisado/cadastrado com segurança.")
        return 0

    elif parsed.command == "add-candidate":
        src = None
        if parsed.source_url:
            src = Source(
                url=parsed.source_url,
                title=parsed.source_title,
                source_type=SourceType.E3,
                supports=["Descoberta de candidato"],
            )
        lead, is_new, reason = research.ingest_candidate(
            name=parsed.name,
            city=parsed.city,
            category=parsed.category,
            neighborhood=parsed.neighborhood,
            phone=parsed.phone,
            initial_source=src,
        )
        if is_new:
            print(f"Candidato cadastrado com sucesso: [{lead.id}] {lead.business.name}")
        else:
            print(f"Candidato já existia ({lead.id}). Fonte anexada ao lead existente.")
            print(f"Motivo: {reason}")
        return 0

    elif parsed.command == "verify-company":
        src = Source(
            url=parsed.source_url,
            title=parsed.source_title,
            source_type=SourceType(parsed.source_type),
            supports=["Verificação de identidade e localização da empresa"],
        )
        try:
            lead = research.verify_company_identity(
                lead_id=parsed.lead_id,
                source=src,
                confirmed_address=parsed.address,
                confirmed_neighborhood=parsed.neighborhood,
            )
            print(f"Identidade verificada com sucesso para [{lead.id}]. Novo status: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "verify-website":
        try:
            lead = research.record_website_verification(
                lead_id=parsed.lead_id,
                website_url=parsed.url,
                website_status=WebsiteStatus(parsed.status),
                notes=parsed.notes,
            )
            print(f"Verificação de website registrada para [{lead.id}].")
            print(f"Status do Site: {lead.business.website_status.value} | Status Pipeline: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "add-responsible":
        src = Source(
            url=parsed.source_url,
            title=parsed.source_title,
            source_type=SourceType(parsed.source_type),
            supports=[f"Vínculo de {parsed.name} como {parsed.role}: {parsed.proof}"],
        )
        try:
            lead, contact, has_conflict = responsible.add_responsible(
                lead_id=parsed.lead_id,
                name=parsed.name,
                role=parsed.role,
                source=src,
                relationship_proof=parsed.proof,
                confidence=ConfidenceLevel(parsed.confidence),
            )
            print(f"Responsável registrado para [{lead.id}]: {contact.name} ({contact.role})")
            print(f"Confiança: {contact.confidence.value} | Status Pipeline: {lead.pipeline_status.value}")
            if has_conflict:
                print("AVISO: Foi detectado conflito com registro anterior. Confiança reduzida.")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "associate-phone":
        src = None
        if parsed.source_url:
            src = Source(
                url=parsed.source_url,
                title=parsed.source_title,
                source_type=SourceType.E2,
                supports=[f"Número {parsed.phone}"],
            )
        try:
            lead, contact = responsible.associate_phone(
                lead_id=parsed.lead_id,
                contact_id=parsed.contact_id,
                phone=parsed.phone,
                source=src,
                is_person_associated=parsed.is_person_associated,
            )
            print(f"Telefone {parsed.phone} associado com sucesso a [{contact.name or 'Empresa'}].")
            print(f"Tipo: {contact.type.value} | Status Pipeline: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "select-contact":
        try:
            lead, best = responsible.select_recommended_contact(parsed.lead_id)
            if best:
                print(f"Contato recomendado definido: [{best.id}] {best.name or 'Empresa'} - {best.phone or 'Sem telefone'}")
            else:
                print(f"Nenhum contato disponível para selecionar no lead [{lead.id}].")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "qualify-lead":
        cls_override = OpportunityClass(parsed.classification) if parsed.classification else None
        try:
            lead = opportunity.qualify_lead(
                lead_id=parsed.lead_id,
                evidence=parsed.evidence,
                hypothesis=parsed.hypothesis,
                uncertainties=parsed.uncertainty,
                classification=cls_override,
            )
            print(f"Lead [{lead.id}] qualificado com sucesso.")
            print(f"Classificação: {lead.opportunity.classification.value} | Status Pipeline: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "prepare-outreach":
        try:
            lead, msg = opportunity.prepare_outreach(parsed.lead_id)
            print(f"Abordagem inicial preparada para [{lead.id}].")
            print(f"Mensagem: \"{msg}\"")
            print(f"Revisão Humana: {lead.outreach.human_review} | Status Pipeline: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "daily-review":
        queue = review.get_review_queue()
        print(f"\nFILA DE REVISÃO DIÁRIA — {len(queue)} lead(s) prontos para decisão:")
        if not queue:
            print("Nenhum lead com status READY_FOR_REVIEW no momento.\n")
            return 0
        for l in queue:
            print(review.render_decision_card(l))
            print()
        return 0

    elif parsed.command == "confirm-sent":
        try:
            lead = conversation.confirm_manual_send(
                lead_id=parsed.lead_id,
                sent_message=parsed.message,
                notes=parsed.notes,
            )
            print(f"Envio manual do WhatsApp confirmado para [{lead.id}]!")
            print(f"Status do Pipeline atualizado para: {lead.pipeline_status.value}")
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "record-response":
        intent_override = ResponseIntent(parsed.intent) if parsed.intent else None
        try:
            lead, conv, handoff_dossier = conversation.process_inbound_response(
                lead_id=parsed.lead_id,
                text=parsed.text,
                intent_override=intent_override,
                notes=parsed.notes,
            )
            print(f"Resposta registrada para [{lead.id}].")
            print(f"Intenção detectada: {conv.intent.value} | Novo Status: {lead.pipeline_status.value}")
            if handoff_dossier:
                print("\nATENÇÃO: LEAD INTERESSADO — HANDOFF EXECUTIVO ACIONADO:")
                print(handoff_dossier)
            return 0
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1

    elif parsed.command == "export-review-html":
        out_path = Path(parsed.out) if parsed.out else None
        generated_file = review.export_html_report(output_path=out_path)
        print(f"Relatório visual de revisão exportado com sucesso para: {generated_file}")
        return 0

    elif parsed.command == "log-query":
        entry = research.log_research_query(
            query=parsed.query,
            purpose=parsed.purpose,
            lead_id=parsed.lead_id,
        )
        print(f"Consulta de pesquisa registrada no log de auditoria: [{entry.id}] '{parsed.query}'")
        return 0

    elif parsed.command == "export-json":
        leads = [l.to_dict() for l in db.list_leads()]
        json_str = json.dumps(leads, indent=2, ensure_ascii=False)
        if parsed.out:
            with open(parsed.out, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"Exportados {len(leads)} leads para {parsed.out}")
        else:
            print(json_str)
        return 0

    elif parsed.command == "serve":
        from src.server import run_server
        server = run_server(port=parsed.port, host=parsed.host)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor CRM encerrado.")
            server.server_close()
        return 0

    elif parsed.command == "audit-leads":
        audit_svc = AdversarialAuditService(db=db)
        summary = audit_svc.audit_all_leads(only_active=True, require_audit_dossier=True)
        print(f"Total auditados: {summary['total_audited']} | Aprovados: {summary['passed']} | Falhas: {summary['failed']} | Colisões de Telefone: {summary['phone_collisions_count']}")
        for r in summary["results"]:
            if not r["passed"]:
                print(f"  [FALHA] {r['business_name']} ({r['lead_id']}): {'; '.join(r['errors'])}")
        return 0 if summary["all_passed"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
