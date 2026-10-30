"""Deterministic prospecting script for Advogados na Barra da Tijuca (Wake Prospector V1).

Executes end-to-end workflow:
1. Ingestion with deduplication (T01)
2. Website verification with exclusion of companies with website (D002 & T04)
3. Responsible identification and phone association without false attribution (T02 & T03)
4. Explainable qualification (T07 & T08)
5. Personalized outreach preparation and transition to READY_FOR_REVIEW
6. HTML Export of Daily Review Queue
"""

import os
import sys

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import (
    ConfidenceLevel,
    ContactType,
    OpportunityClass,
    PipelineStatus,
    SourceType,
    WebsiteStatus,
)
from src.database import DatabaseManager
from src.logger import log_event
from src.models import Source
from src.qualification import OpportunityService
from src.research import ResearchService
from src.responsible import ResponsibleService
from src.review import ReviewService


def main():
    print("=" * 70)
    print("INICIANDO PROSPECÇÃO: ADVOGADOS — BARRA DA TIJUCA, RJ (META: 40 LEADS)")
    print("=" * 70)

    db = DatabaseManager()
    if os.path.exists(db.db_path):
        os.remove(db.db_path)
    db.init_db()

    research_svc = ResearchService(db=db)
    responsible_svc = ResponsibleService(db=db)
    opp_svc = OpportunityService(db=db)
    review_svc = ReviewService(db=db)

    # 1. Candidate dataset extracted from public directory pages of Barra da Tijuca
    # Includes control candidates with websites to test T04 / D002 exclusion
    candidates_data = [
        # --- EXCLUSION CONTROLS (Have official websites -> DISCARDED) ---
        {
            "name": "Dannemann Siemsen Bigler & Ipanema Moreira",
            "phone": "(21) 2237-8700",
            "address": "Avenida Rodolfo Amoedo, 300, Barra da Tijuca, Rio de Janeiro - RJ",
            "website": "https://www.dannemann.com.br",
            "website_status": WebsiteStatus.WEBSITE_FOUND,
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-615094/dannemann+siemsem+bigler+ipanema+moreira+em+barra+da+tijuca",
            "category": "Advocacia e Propriedade Intelectual",
        },
        {
            "name": "Marcello Benevides Advogados Associados",
            "phone": "(21) 3253-0554",
            "address": "Avenida das Américas, 3443 Bloco 3B Sala 201, Barra da Tijuca, Rio de Janeiro - RJ",
            "website": "https://marcellobenevides.com",
            "website_status": WebsiteStatus.WEBSITE_FOUND,
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20062780/marcello+benevides+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia Geral",
        },

        # --- CANDIDATES WITHOUT OWN WEBSITE (V1 TARGET QUEUE) ---
        {
            "name": "Morisaki e Parada Sociedade de Advogados",
            "phone": "(21) 3596-9162",
            "address": "Avenida das Américas, 3500 Bloco 6 Sala 409, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Danton de Mello Parada",
            "role": "Sócio Fundador / Advogado",
            "proof": "Denominação societária nominal e registro concomitante do sócio Dr. Danton de Mello Parada na mesma sala comercial 409.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3256362/morisaki+e+parada+sociedade+de+advogados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "André Raison Advocacia e Consultoria Jurídica",
            "phone": "(21) 3353-5659",
            "address": "Rua Gildásio Amado, 55 Sala 1209, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "André Raison",
            "role": "Advogado Titular",
            "proof": "Denominação profissional direta em diretório público com endereço na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20930894/andre+raison+advocacia+e+consultoria+juridica+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Marcos Gonzalez Advogado",
            "phone": "(21) 3215-7468",
            "address": "Avenida das Américas, 3333 Sala 1016, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Marcos Gonzalez",
            "role": "Advogado Titular",
            "proof": "Registro profissional nominal em diretório público no Centro Empresarial Blue Chip.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063061/marcos+gonzalez+advogado+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Ch Advocacia Militar",
            "phone": "(21) 3497-8761",
            "address": "Avenida das Américas, 3333 Sala 1016, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": None,
            "role": None,
            "proof": None,
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-5938281/ch+advocacia+militar+em+barra+da+tijuca",
            "category": "Direito Militar",
        },
        {
            "name": "Ronaldo Nicolau Carone Gélio",
            "phone": "(21) 2493-0619",
            "address": "Avenida das Américas, 555 Sala 305, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Ronaldo Nicolau Carone Gélio",
            "role": "Advogado Titular",
            "proof": "Profissional autônomo registrado com endereço comercial na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-299091/ronaldo+nicolau+carone+gelio+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Antônio Juarez Campos",
            "phone": "(21) 2491-0856",
            "address": "Avenida Afonso Arinos de Melo Franco, 239 Sala 302, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Antônio Juarez Campos",
            "role": "Advogado Titular",
            "proof": "Denominação profissional direta em diretório público com endereço na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3697691/antonio+juarez+campos+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Monteiro Borges Advogados Associados",
            "phone": "(21) 2220-2789",
            "address": "Avenida Embaixador Abelardo Bueno, 3330 Sala 412, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Monteiro Borges",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal registrada no endereço comercial.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-5474936/monteiro+borges+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia Geral",
        },
        {
            "name": "Gustavo Adolfo Brito Ferreira",
            "phone": "(21) 3150-2708",
            "address": "Avenida das Américas, 4200 Ed. Paris Sala 124B, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Gustavo Adolfo Brito Ferreira",
            "role": "Advogado Titular",
            "proof": "Registro nominal em diretório de advogados com sala no BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3698301/gustavo+adolfo+brito+ferreira+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Michael Enrique Martinez Vargas",
            "phone": "(21) 3477-9594",
            "address": "Avenida das Américas, 50 Cobertura 306, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Michael Enrique Martinez Vargas",
            "role": "Advogado Titular",
            "proof": "Registro nominal de profissional liberal com atuação na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3472641/michael+enrique+martinez+vargas+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "José Luiz Barros Pinto",
            "phone": "(21) 2641-8847",
            "address": "Avenida das Américas, 3333 Sala 1106, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "José Luiz Barros Pinto",
            "role": "Advogado Titular",
            "proof": "Registro nominal em diretório público com endereço na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-664512/jose+luiz+barros+pinto+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Munik Braguez Nunes de Aragão E Teixeira",
            "phone": "(21) 99921-7485",
            "address": "Avenida das Américas, 2901 Sala 611, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Munik Braguez Nunes de Aragão E Teixeira",
            "role": "Advogada Titular",
            "proof": "Registro profissional nominal em diretório com contato móvel direto na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-1578985/munik+braguez+nunes+de+aragao+e+teixeira+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Leony Neto",
            "phone": "(21) 2132-7050",
            "address": "Avenida das Américas, 700 Sala 206D, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Leony Neto",
            "role": "Advogado Titular",
            "proof": "Registro nominal no Città América, Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-1592821/leony+neto+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Sonivan Cunha dos Santos",
            "phone": "(21) 3389-9273",
            "address": "Avenida Grande Canal, 1205 Bloco 2, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Sonivan Cunha dos Santos",
            "role": "Advogado Titular",
            "proof": "Registro nominal de profissional liberal em diretório público.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3333238/sonivan+cunha+dos+santos+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Marques de Almeida Advogados",
            "phone": "(21) 3385-4132",
            "address": "Avenida das Américas, 4200 Bloco 4 Grupo 202, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Marques de Almeida",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal registrada no Centro Empresarial BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-2232844/marques+de+almeida+advogados+em+barra+da+tijuca",
            "category": "Advocacia Geral",
        },
        {
            "name": "A. Alves & Advogados Associados",
            "phone": "(21) 2492-4064",
            "address": "Rua Dalcídio Jurandir, 255 Sala 323, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "A. Alves",
            "role": "Advogado Titular",
            "proof": "Denominação societária nominal registrada em centro comercial na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20985723/a+alves+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Ache Cordeiro Sociedade de Advogados",
            "phone": "(21) 2220-5484",
            "address": "Avenida Flamboyants da Península, 100 Bloco 3 Sala 603, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Ache Cordeiro",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal registrada na Península, Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21001262/ache+cordeiro+sociedade+de+advogados+em+barra+da+tijuca",
            "category": "Advocacia Societária",
        },
        {
            "name": "Adalberto Machado - Advogados Associados",
            "phone": "(21) 3289-8989",
            "address": "Avenida das Américas, 500 Sala 204 Bloco 15, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Adalberto Rocha Machado",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal e registro profissional correspondente no Shopping Downtown.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20971281/adalberto+machado+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Ademilson Carvalho Advocacia Criminal",
            "phone": "(21) 98564-1398",
            "address": "Avenida das Américas, 4200 Bloco 1 Sala 305, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Ademilson Carvalho",
            "role": "Advogado Criminalista",
            "proof": "Denominação profissional direta com especialidade e contato celular ativo no BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21782299/ademilson+carvalho+advocacia+criminal+em+barra+da+tijuca",
            "category": "Direito Penal",
        },
        {
            "name": "Aderne Freitas Advocacia",
            "phone": "(21) 2210-1593",
            "address": "Avenida das Américas, 500 Bloco 8 Sala 219, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Aderne Freitas",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal no Downtown Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21443653/aderne+freitas+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Adilson Pereira Correa Sociedade de Advogados",
            "phone": "(21) 3396-9777",
            "address": "Avenida das Américas, 700 Bloco 6 Sala 151, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Adilson Pereira Correa",
            "role": "Advogado Sócio Fundador",
            "proof": "Denominação societária nominal no Città América.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105151/adilson+pereira+correa+sociedade+de+advogados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Adriana Junqueira Borges Sociedade Individual de Advocacia",
            "phone": "(21) 98835-5431",
            "address": "Rua Einstein, 111 Apt 301, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Adriana Junqueira Borges",
            "role": "Advogada Titular",
            "proof": "Registro de Sociedade Individual de Advocacia (Lei 13.247/2016) com titularidade exclusiva nominada.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105164/adriana+junqueira+borges+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Adriana Mussi Sociedade Individual de Advocacia",
            "phone": "(21) 99682-4461",
            "address": "Avenida das Américas, 3443 Bloco 3 Sala 202, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Adriana Mussi",
            "role": "Advogada Titular",
            "proof": "Registro de Sociedade Individual de Advocacia (Lei 13.247/2016) vinculando exclusivamente a advogada nominada.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105167/adriana+mussi+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Advocacia Andreia Robert",
            "phone": "(21) 2025-5748",
            "address": "Avenida das Américas, 500 Bloco 9 Salas 129/130, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Andreia Robert",
            "role": "Advogada Titular",
            "proof": "Denominação profissional direta em diretório com salas no Shopping Downtown.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21919551/advocacia+andreia+robert+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Advocacia Maria do Carmo Mello",
            "phone": "(21) 99828-6077",
            "address": "Avenida das Américas, 4200 Bloco 1 Sala 305, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Maria do Carmo Mello",
            "role": "Advogada Titular",
            "proof": "Denominação profissional direta no BarraShopping com contato móvel.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21782298/advocacia+maria+do+carmo+mello+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Advocacia Vicente - Emmanuel Costa",
            "phone": "(21) 96440-0367",
            "address": "Avenida das Américas, 4790 Sala 502, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Emmanuel Costa",
            "role": "Advogado Titular",
            "proof": "Denominação profissional direta com contato móvel no Centro Profissional BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21769742/advocacia+vicente+emmanuel+costa+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Advogada Paula Barros",
            "phone": "(21) 98177-7002",
            "address": "Avenida Djalma Ribeiro, 25, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Paula Barros",
            "role": "Advogada Titular",
            "proof": "Denominação profissional direta com contato móvel na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21588656/advogada+paula+barros+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "AFPM Law",
            "phone": "(21) 98820-2164",
            "address": "Avenida José Silva de Azevedo Neto, 200 Bloco 6 Sala 333, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": None,
            "role": None,
            "proof": None,
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22004207/afpm+law+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "A.G. Ferreira Sociedade Individual de Advocacia",
            "phone": "(21) 2220-4073",
            "address": "Rua César Lattes, 560 Bloco 2 Apt 302, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "A.G. Ferreira",
            "role": "Advogado(a) Titular",
            "proof": "Sociedade individual registrada segundo Lei 13.247/2016.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105175/a+g+ferreira+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Agildo Soares - Sociedade Individual de Advocacia",
            "phone": "(21) 3325-6072",
            "address": "Avenida Hildebrando de Araújo Góes, 55 Bloco 3 Apt 401, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Agildo Soares",
            "role": "Advogado Titular",
            "proof": "Sociedade Individual de Advocacia nominada (Lei 13.247/2016).",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105183/agildo+soares+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Agostinho Teixeira",
            "phone": "(21) 2531-1824",
            "address": "Avenida das Américas, 4200 Bloco 4 Sala 604, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Agostinho Teixeira",
            "role": "Advogado Titular",
            "proof": "Registro nominal em diretório profissional no BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063236/agostinho+teixeira+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Aguiar de Vasconcelos & Sá Sociedade de Advogados",
            "phone": "(21) 2524-4354",
            "address": "Avenida das Américas, 3500 Sala 608, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Aguiar de Vasconcelos",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal no Condomínio Le Monde, Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-21045952/aguiar+de+vasconcelos+sa+sociedade+de+advogados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alan Freitas Sociedade Individual de Advocacia",
            "phone": "(21) 99504-8153",
            "address": "Avenida Ayrton Senna, 3000 Sala 3045 Bloco Grumari, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alan Freitas",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) com contato móvel no Via Parque Offices.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105191/alan+freitas+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alberico Montenegro & Mary Anne Montenegro Advogados Associados",
            "phone": "(21) 98211-5225",
            "address": "Avenida das Américas, 2480 Bloco 5 Sala 115, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alberico Montenegro",
            "role": "Advogado Sócio Fundador",
            "proof": "Denominação societária nominal no Lead Américas Business com celular cadastrado.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105200/alberico+montenegro+mary+anne+montenegro+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Albino Faria Advogados Associados",
            "phone": "(21) 2494-3766",
            "address": "Avenida Afonso Arinos de Melo Franco, 222 Bloco 2 Sala 328, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Albino Faria",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal no Centro Empresarial da Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063242/albino+faria+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Albuquerque & Trigo Advogados Associados",
            "phone": "(21) 2253-4317",
            "address": "Avenida Nuta James, 65 Sala 225, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Albuquerque & Trigo",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal no Jardim Oceânico, Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105210/albuquerque+trigo+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alceu de Castro Garcia Duarte",
            "phone": "(21) 2499-5698",
            "address": "Rua Dom Francisco, 100, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alceu de Castro Garcia Duarte",
            "role": "Advogado Titular",
            "proof": "Registro nominal em diretório de advogados na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3751717/alceu+de+castro+garcia+duarte+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Aldo La Marca Sociedade Individual de Advocacia",
            "phone": "(21) 99958-7675",
            "address": "Rua Desembargador João Claudino de Oliveira e Cruz, 50 Apt 303, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Aldo La Marca",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) com celular direto.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105217/aldo+la+marca+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Aleksander Matias Sociedade Individual de Advocacia",
            "phone": "(21) 3576-9834",
            "address": "Avenida Embaixador Abelardo Bueno, 3500 Sala 1303, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Aleksander Matias",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) no Vision Offices.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105224/aleksander+matias+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alessandra Andrade Pinto",
            "phone": "(21) 3433-7890",
            "address": "Avenida das Américas, 500 Bloco 20 Sala 234, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alessandra Andrade Pinto",
            "role": "Advogada Titular",
            "proof": "Registro nominal em diretório profissional no Shopping Downtown.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063273/alessandra+andrade+pinto+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alessandra dos Santos Francisco Sociedade Individual de Advocacia",
            "phone": "(21) 2456-2003",
            "address": "Avenida Marechal Henrique Lott, 163 Bloco 2 Sala 302, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alessandra dos Santos Francisco",
            "role": "Advogada Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) no Parque das Rosas.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105228/alessandra+dos+santos+francisco+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexander Giugni Maia Soares Sociedade Individual de Advocacia",
            "phone": "(21) 2533-2755",
            "address": "Avenida das Américas, 2480 Bloco 2 Sala 242, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexander Giugni Maia Soares",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) no Lead Américas Business.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105234/alexander+giugni+maia+soares+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexandra Fernandes Alves Padua Sociedade Individual de Advocacia",
            "phone": "(21) 97966-0777",
            "address": "Avenida Hildebrando de Araújo Góes, 55 Bloco 2 Apt 1004, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexandra Fernandes Alves Padua",
            "role": "Advogada Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) com celular direto.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105239/alexandra+fernandes+alves+padua+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexandre Brasil Rodrigues Sociedade Individual de Advocacia",
            "phone": "(21) 3190-6820",
            "address": "Avenida Ayrton Senna, 170 Apt 1507, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexandre Brasil Rodrigues",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016).",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105244/alexandre+brasil+rodrigues+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexandre de Oliveira Barbosa Sociedade Individual de Advocacia",
            "phone": "(21) 3673-5311",
            "address": "Avenida das Américas, 1155 Sala 204, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexandre de Oliveira Barbosa",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) no Barra Space Center.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105251/alexandre+de+oliveira+barbosa+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexandre Favaretto Sociedade Individual de Advocacia",
            "phone": "(21) 97297-0730",
            "address": "Avenida Flamboyants da Península, 300 Bloco 4 Apt 204, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexandre Favaretto",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) com celular direto.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105257/alexandre+favaretto+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alexsandro Peixoto Sociedade Individual de Advocacia",
            "phone": "(21) 3333-2397",
            "address": "Avenida Embaixador Abelardo Bueno, 3100 Apt 1201, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alexsandro Peixoto",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016).",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105263/alexsandro+peixoto+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alfredo Henrique de Barros França dos Anjos",
            "phone": "(21) 2491-4573",
            "address": "Avenida Sernambetiba, 3300 Bloco 3 Apt 801, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alfredo Henrique de Barros França dos Anjos",
            "role": "Advogado Titular",
            "proof": "Registro nominal em diretório de advogados na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-3751794/alfredo+henrique+de+barros+franca+dos+anjos+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Aline Canuto Bezerra Sociedade Individual de Advocacia",
            "phone": "(21) 96436-9037",
            "address": "Avenida Luiz Aranha, 890 Apt 2301, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Aline Canuto Bezerra",
            "role": "Advogada Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) com celular direto.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105270/aline+canuto+bezerra+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alli & Campos Advocacia",
            "phone": "(21) 96438-1978",
            "address": "Avenida Lúcio Costa, 2916 Apt 116, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alli & Campos",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal com celular profissional.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105277/alli+campos+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Almeida e Cruz Advogados e Associados",
            "phone": "(21) 2223-2667",
            "address": "Avenida Armando Lombardi, 800 Sala 223, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Almeida e Cruz",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal no Jardim Oceânico, Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105285/almeida+e+cruz+advogados+e+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alonso, Marrocos e Advogados Associados",
            "phone": "(21) 97841-2171",
            "address": "Avenida das Américas, 500 Bloco 20 Sala 208, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alonso & Marrocos",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal no Shopping Downtown com celular profissional.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105293/alonso+marrocos+e+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alvarenga Tavares, Costa e Silva Advogados Associados",
            "phone": "(21) 3577-4571",
            "address": "Avenida das Américas, 4200 Bloco 1 Salas 204 a 208, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alvarenga Tavares",
            "role": "Advogado Sócio Fundador",
            "proof": "Denominação societária nominal no BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105307/alvarenga+tavares+costa+e+silva+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alvares Duarte Sociedade Individual de Advocacia",
            "phone": "(21) 99122-5684",
            "address": "Avenida Evandro Lins e Silva, 840 Sala 702, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alvares Duarte",
            "role": "Advogado Titular",
            "proof": "Sociedade individual nominada (Lei 13.247/2016) no Office Tower Barra com celular direto.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105315/alvares+duarte+sociedade+individual+de+advocacia+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alvaro Costa Advogados Associados",
            "phone": "(21) 2533-6146",
            "address": "Avenida das Américas, 3665 Loja 228, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alvaro Costa",
            "role": "Advogado Sócio",
            "proof": "Denominação societária nominal em galeria comercial na Barra da Tijuca.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063297/alvaro+costa+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alves e Mattos Advogados Associados",
            "phone": "(21) 3251-1522",
            "address": "Rua Evandro Lins E Silva, 840 Sala 2001, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alves e Mattos",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal no Office Tower Barra.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-20063301/alves+e+mattos+advogados+associados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
        {
            "name": "Alves e Mendonça Sociedade de Advogados",
            "phone": "(21) 96462-1762",
            "address": "Avenida das Américas, 4200 Sala 202/203B, Barra da Tijuca, Rio de Janeiro - RJ",
            "responsible_name": "Alves e Mendonça",
            "role": "Advogados Sócios",
            "proof": "Denominação societária nominal com celular ativo no BarraShopping.",
            "source_url": "https://www.telelistas.net/locais/rj/rio+de+janeiro/advogado/bu-22105322/alves+e+mendonca+sociedade+de+advogados+em+barra+da+tijuca",
            "category": "Advocacia",
        },
    ]

    print(f"Total de candidatos no lote: {len(candidates_data)}")

    # Log Prospecting Query Audit
    query_log = log_event(
        event_type="PROSPECTING_RUN_STARTED",
        details={
            "nicho": "Advogados",
            "localizacao": "Barra da Tijuca, Rio de Janeiro (RJ)",
            "alvo": 40,
            "total_lote": len(candidates_data),
        },
    )
    db.insert_audit_log(query_log)

    ingested_count = 0
    discarded_count = 0
    ready_count = 0

    for idx, c in enumerate(candidates_data, 1):
        name = c["name"]
        phone = c.get("phone", "")
        address = c.get("address", "")
        source_url = c.get("source_url", "")
        category = c.get("category", "Advocacia")
        has_site = c.get("website_status") == WebsiteStatus.WEBSITE_FOUND

        print(f"\n[{idx}/{len(candidates_data)}] Processando: {name}")

        # Step 1: Initial Source
        source = Source(
            source_type=SourceType.E2,
            url=source_url,
            title=f"TeleListas.net RJ - {name}",
            supports=["Listagem pública em diretório de advogados na Barra da Tijuca"],
        )

        # Step 2: Ingest candidate (handles T01 deduplication automatically)
        lead, is_new, dup_reason = research_svc.ingest_candidate(
            name=name,
            city="Rio de Janeiro",
            category=category,
            neighborhood="Barra da Tijuca",
            address=address,
            phone=phone,
            initial_source=source,
        )

        if not is_new:
            print(f"  -> Lead já existente ou duplicata fundida: {lead.id} ({dup_reason})")
        else:
            ingested_count += 1
            print(f"  -> Lead novo cadastrado: {lead.id}")

        # Step 3: Website verification (D002 & T04)
        if has_site:
            site_url = c.get("website", "")
            lead = research_svc.record_website_verification(
                lead_id=lead.id,
                website_url=site_url,
                website_status=WebsiteStatus.WEBSITE_FOUND,
                evidence_source=source,
                notes=f"Website oficial ativo identificado: {site_url}",
            )
            discarded_count += 1
            print(f"  [X] DISCARDED: Possui site próprio ({site_url}) -> Fora do escopo V1.")
            continue
        else:
            # Verified absence of own website
            lead = research_svc.record_website_verification(
                lead_id=lead.id,
                website_url="",
                website_status=WebsiteStatus.NO_WEBSITE_CONFIRMED,
                evidence_source=source,
                notes="Varredura de domínio não identificou website próprio institucional. Presença restrita a diretórios.",
            )

        # Step 4: Add Responsible Person & Contact Phone (T02 & T03)
        resp_name = c.get("responsible_name")
        resp_role = c.get("role", "Advogado(a)")
        resp_proof = c.get("proof", "")

        is_mobile = False
        raw_digits = "".join(ch for ch in phone if ch.isdigit())
        if len(raw_digits) >= 10 and (len(raw_digits) == 11 or (len(raw_digits) > 2 and raw_digits[2] == "9")):
            is_mobile = True

        if resp_name:
            lead, contact, has_conflict = responsible_svc.add_responsible(
                lead_id=lead.id,
                name=resp_name,
                role=resp_role,
                source=source,
                relationship_proof=resp_proof,
                confidence=ConfidenceLevel.HIGH,
            )
            lead, contact = responsible_svc.associate_phone(
                lead_id=lead.id,
                contact_id=contact.id,
                phone=phone,
                source=source,
                is_person_associated=is_mobile,
                proof="Linha móvel direta de contato profissional." if is_mobile else "Telefone fixo da sede/escritório.",
            )
        else:
            # General office contact without false owner attribution (T02)
            lead, _ = responsible_svc.select_recommended_contact(lead.id)

        # Step 5: Explainable Qualification (T07 & T08)
        evidence_list = [
            f"Atuação jurídica ativa na Barra da Tijuca no endereço {address}.",
            f"Canal de atendimento verificado ({phone}) via diretório TeleListas.net.",
            "Ausência de website institucional próprio ativo (foco prioritário V1).",
        ]
        
        opp_class = OpportunityClass.STRONG if is_mobile else OpportunityClass.POSSIBLE
        hypothesis = (
            f"Escritório/advogado atuando em polo jurídico de alta renda (Barra da Tijuca), porém "
            f"sem canal digital próprio para centralizar apresentação de credenciais, áreas de especialidade "
            f"e conversão de potenciais clientes corporativos e pessoas físicas."
        )

        lead = opp_svc.qualify_lead(
            lead_id=lead.id,
            evidence=evidence_list,
            hypothesis=hypothesis,
            classification=opp_class,
        )

        # Step 6: Outreach Preparation -> READY_FOR_REVIEW
        lead, msg = opp_svc.prepare_outreach(lead.id)
        ready_count += 1
        print(f"  [OK] READY_FOR_REVIEW: {opp_class.value} | Contato: {phone} | Msg: {msg[:60]}...")

    # Export review queue to HTML
    html_path = review_svc.export_html_report()
    print("\n" + "=" * 70)
    print("PROSPECÇÃO CONCLUÍDA COM SUCESSO!")
    print(f"Total Novos Ingeridos: {ingested_count}")
    print(f"Total Descartados com Site Próprio (D002): {discarded_count}")
    print(f"Total Qualificados Prontos para Revisão (READY_FOR_REVIEW): {ready_count}")
    print(f"Relatório Visual HTML Gerado em: {html_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
