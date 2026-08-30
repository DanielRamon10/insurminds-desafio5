"""Galeria de mensagens por cenário — tarefa E.4.

O enunciado pede para "demonstrar diferentes tipos de mensagens para diferentes
cenários". Este script produz `docs/GALERIA_MENSAGENS.md` executando o pipeline
de verdade: cada mensagem sai do mesmo caminho da demonstração, com o evento e
os números que a dispararam ao lado — nada é escrito à mão.

    python -m scripts.gerar_galeria              # usa o LLM se houver chave
    python -m scripts.gerar_galeria --sem-llm    # só o redator por template

Sem chave configurada o resultado é o mesmo do `--sem-llm`: o orquestrador cai
no template, e a galeria registra isso em cada mensagem.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.orchestrator import gerar_notificacao
from app.config import ConfigLLM, obter_api_key
from app.domain.cenarios import previsao_cenario
from app.domain.eventos import classificar
from app.domain.regras import carregar_regras
from app.schemas import (
    Canal,
    Cidade,
    EventoClimatico,
    LIMITE_CARACTERES,
    Notificacao,
    Segurado,
    Severidade,
    TipoApolice,
    TipoEvento,
)

CIDADE = Cidade(
    nome="Curitiba", uf="PR", latitude=-25.43, longitude=-49.27, codigo_ibge="4106902"
)

#: Rótulo legível de cada medida, para a coluna "o que disparou".
ROTULO_MEDIDA = {
    "precipitacao_mm_h": ("chuva na hora mais forte", "mm/h"),
    "precipitacao_mm_janela": ("chuva acumulada em 24 h", "mm"),
    "rajada_km_h": ("rajada máxima", "km/h"),
    "cape_j_kg": ("energia da tempestade (CAPE)", "J/kg"),
    "nivel_congelamento_m": ("altura onde congela", "m"),
    "codigo_wmo": ("código de trovoada (WMO)", ""),
}


def segurado(nome: str, apolice: TipoApolice, canal: Canal) -> Segurado:
    return Segurado(
        id=f"GAL-{abs(hash((nome, apolice.value, canal.value))) % 1000:03d}",
        nome=nome, tipo_apolice=apolice, cidade=CIDADE.nome, uf=CIDADE.uf,
        latitude=CIDADE.latitude, longitude=CIDADE.longitude, canal=canal,
    )


def evento_do_cenario(nome_cenario: str, tipo: TipoEvento) -> EventoClimatico:
    """Roda o cenário forçado pelo classificador real e devolve o evento pedido."""
    previsao = previsao_cenario(nome_cenario, CIDADE)
    for evento in classificar(previsao, REGRAS):
        if evento.tipo is tipo:
            return evento
    raise RuntimeError(f"cenario '{nome_cenario}' nao produziu evento {tipo.value}")


def medidas_legiveis(evento: EventoClimatico) -> str:
    partes = []
    for campo, (rotulo, unidade) in ROTULO_MEDIDA.items():
        valor = getattr(evento.medidas, campo, None)
        if valor is None:
            continue
        numero = f"{valor:g}"
        partes.append(f"{rotulo} {numero} {unidade}".strip())
    return "; ".join(partes) if partes else "—"


def bloco(titulo: str, evento: EventoClimatico, notificacao: Notificacao) -> list[str]:
    origem = "agente redator (LLM)" if notificacao.gerada_por_llm else "redator por template"
    limite = LIMITE_CARACTERES[notificacao.canal]
    return [
        f"### {titulo}",
        "",
        f"**Disparado por:** {medidas_legiveis(evento)}",
        "",
        f"> {notificacao.mensagem}",
        "",
        f"`{notificacao.canal.value.upper()}` · {len(notificacao.mensagem)}/{limite} "
        f"caracteres · {origem}",
        "",
    ]


def gerar(usar_llm: bool) -> str:
    linhas: list[str] = [
        "# Galeria de mensagens por cenário",
        "",
        "Tarefa **E.4**. Cada mensagem abaixo saiu do pipeline real — cenário",
        "climático forçado, classificado pelos limiares de `data/regras.yaml`,",
        "cruzado com a base de segurados e redigido pelos agentes. Nenhuma foi",
        "escrita à mão.",
        "",
        f"Gerada em {datetime.now():%d/%m/%Y às %H:%M} por "
        f"`python -m scripts.gerar_galeria{'' if usar_llm else ' --sem-llm'}`.",
        "",
        "---",
        "",
        "## 1. Os sete cenários ativos",
        "",
        "A matriz de negócio cobre sete pares evento × apólice. `raio × automotiva`",
        "fica de fora por decisão do corretor: o veículo age como gaiola de Faraday",
        "e não há recomendação preventiva honesta a fazer.",
        "",
    ]

    ativos = [
        (TipoEvento.CHUVA_INTENSA, "chuva_intensa", TipoApolice.RESIDENCIAL, Canal.SMS, "Ana Ribeiro"),
        (TipoEvento.CHUVA_INTENSA, "chuva_intensa", TipoApolice.AUTOMOTIVA, Canal.PUSH, "Bruno Tavares"),
        (TipoEvento.RAIO, "raio", TipoApolice.RESIDENCIAL, Canal.PUSH, "Carla Menezes"),
        (TipoEvento.VENTO_FORTE, "vento_forte", TipoApolice.RESIDENCIAL, Canal.SMS, "Diego Prado"),
        (TipoEvento.VENTO_FORTE, "vento_forte", TipoApolice.AUTOMOTIVA, Canal.PUSH, "Elisa Fontes"),
        (TipoEvento.GRANIZO, "granizo", TipoApolice.RESIDENCIAL, Canal.EMAIL, "Hugo Quintela"),
        (TipoEvento.GRANIZO, "granizo", TipoApolice.AUTOMOTIVA, Canal.PUSH, "Iara Souto"),
    ]

    for tipo, cenario, apolice, canal, nome in ativos:
        evento = evento_do_cenario(cenario, tipo)
        notificacao = gerar_notificacao(
            segurado(nome, apolice, canal), evento, REGRAS, usar_llm=usar_llm
        )
        titulo = (
            f"{tipo.value.replace('_', ' ').capitalize()} · "
            f"{evento.severidade.value} · apólice {apolice.value}"
        )
        linhas += bloco(titulo, evento, notificacao)

    # ------------------------------------------------------------------
    linhas += [
        "---",
        "",
        "## 2. Mesma tempestade, apólices diferentes",
        "",
        "O contraste que justifica cruzar evento com apólice: o mesmo evento, na",
        "mesma cidade e na mesma hora, rende orientações opostas conforme o que o",
        "segurado tem a proteger.",
        "",
    ]
    evento = evento_do_cenario("chuva_intensa", TipoEvento.CHUVA_INTENSA)
    for apolice, nome in [(TipoApolice.RESIDENCIAL, "Ana Ribeiro"),
                          (TipoApolice.AUTOMOTIVA, "Bruno Tavares")]:
        notificacao = gerar_notificacao(
            segurado(nome, apolice, Canal.PUSH), evento, REGRAS, usar_llm=usar_llm
        )
        linhas += bloco(f"Apólice {apolice.value}", evento, notificacao)

    # ------------------------------------------------------------------
    linhas += [
        "---",
        "",
        "## 3. Mesmo evento, canais diferentes",
        "",
        "O limite do canal muda o que cabe. O SMS corta em fronteira de palavra; o",
        "e-mail acomoda a orientação inteira, separada em blocos.",
        "",
    ]
    evento = evento_do_cenario("granizo", TipoEvento.GRANIZO)
    for canal in [Canal.SMS, Canal.PUSH, Canal.EMAIL]:
        notificacao = gerar_notificacao(
            segurado("Iara Souto", TipoApolice.AUTOMOTIVA, canal),
            evento, REGRAS, usar_llm=usar_llm,
        )
        linhas += bloco(f"Canal {canal.value.upper()} (limite {LIMITE_CARACTERES[canal]})",
                        evento, notificacao)

    # ------------------------------------------------------------------
    linhas += [
        "---",
        "",
        "## 4. Atenção e alerta",
        "",
        "As duas severidades existem para graduar a urgência sem duplicar as regras.",
        "No redator por template a graduação aparece no rótulo de abertura e no número",
        "citado — a orientação preventiva é a mesma, porque a do especialista não muda",
        "com a intensidade. É o agente redator com LLM que ajusta também o tom: o",
        "prompt pede *sem alarmismo* em atenção e *mais urgente, sem gerar pânico* em",
        "alerta. Rodando esta galeria com uma chave configurada, a diferença entre os",
        "dois blocos abaixo fica bem maior.",
        "",
    ]
    for cenario, rotulo in [("vento_forte_atencao", "atenção"), ("vento_forte", "alerta")]:
        evento = evento_do_cenario(cenario, TipoEvento.VENTO_FORTE)
        notificacao = gerar_notificacao(
            segurado("Elisa Fontes", TipoApolice.AUTOMOTIVA, Canal.PUSH),
            evento, REGRAS, usar_llm=usar_llm,
        )
        linhas += bloco(f"Vento forte · severidade {rotulo}", evento, notificacao)

    # ------------------------------------------------------------------
    llm_usado = any("(LLM)" in linha for linha in linhas)
    linhas += [
        "---",
        "",
        "## Como reproduzir",
        "",
        "```",
        "python -m scripts.gerar_galeria            # com LLM, se houver chave no .env",
        "python -m scripts.gerar_galeria --sem-llm  # só o redator por template",
        "```",
        "",
    ]
    if not llm_usado:
        linhas += [
            "> **Nota.** Esta edição saiu inteira pelo redator por template — o caminho",
            "> determinístico da tarefa C.4, que assume quando não há chave de LLM",
            "> configurada, quando a cota do dia acaba ou quando o guardrail reprova a",
            "> mensagem do modelo. Rodando com uma chave no `.env`, o mesmo comando",
            "> regenera esta galeria com as mensagens do agente redator.",
            "",
        ]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera docs/GALERIA_MENSAGENS.md (E.4)")
    parser.add_argument(
        "--sem-llm", action="store_true",
        help="redige so por template, sem chamar o LLM",
    )
    argumentos = parser.parse_args()

    usar_llm = not argumentos.sem_llm
    if usar_llm and not obter_api_key(ConfigLLM().provedor):
        print("(sem chave no .env — a galeria sai pelo redator por template)")

    destino = Path(__file__).resolve().parent.parent / "docs" / "GALERIA_MENSAGENS.md"
    destino.write_text(gerar(usar_llm), encoding="utf-8")
    print(f"galeria escrita em {destino}")


REGRAS = carregar_regras()

if __name__ == "__main__":
    main()
