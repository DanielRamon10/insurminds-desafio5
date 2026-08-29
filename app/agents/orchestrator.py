"""Orquestrador (C.1). Encadeia as quatro frentes numa passagem só:

    coleta (A) -> classificação e regras (B) -> redação (C) -> guardrail -> fallback

Duas fronteiras importam aqui, e ambas apontam para a frente B como fonte de
verdade:

* **O que é um evento** vem de `domain.eventos.classificar()`, que aplica os
  limiares de `data/regras.yaml` — definidos pelo corretor do grupo, não por
  chute de quem programa.
* **Quem deve ser avisado, e do quê** vem de `Regras.recomendacao()`. A mesma
  chamada devolve a orientação preventiva que o especialista escreveu para
  aquele par evento × apólice, e é ela que viaja no `regra_acionada` até o
  prompt do redator. Sem isso a mensagem seria genérica: o valor da recomendação
  é justamente ser específica da combinação.
"""

from __future__ import annotations

import logging
from typing import Iterable, NamedTuple

from ..clients import inmet, open_meteo
from ..domain.eventos import classificar
from ..domain.regras import Regras, carregar_regras
from ..schemas import Cidade, EventoClimatico, Notificacao, Segurado
from . import fallback, guardrails, redator
from .llm import LLMIndisponivel

log = logging.getLogger(__name__)


class DecisaoNotificar(NamedTuple):
    """Este segurado deve ser avisado deste evento, por este motivo.

    `regra_acionada` carrega a recomendação preventiva de `data/regras.yaml`,
    que é o que dá conteúdo específico à mensagem.
    """

    segurado: Segurado
    evento: EventoClimatico
    regra_acionada: str


def _coletar_eventos(cidades: list[Cidade], regras: Regras) -> list[EventoClimatico]:
    """Previsão real de cada cidade, classificada pelos limiares do especialista.

    Os avisos do INMET (A.4) entram como enriquecimento: anexam-se ao evento já
    classificado, sem nunca criar nem remover um — a classificação é nossa, e a
    granularidade do aviso oficial é grosseira demais para decidir por conta
    própria (um único aviso chega a cobrir quase dois mil municípios).
    """
    previsoes, falhas = open_meteo.buscar_varias(cidades)
    for cidade, motivo in falhas:
        log.warning("sem previsao para %s: %s", cidade, motivo)

    alertas = inmet.buscar_alertas_tolerante()
    por_chave = {(c.nome, c.uf): c for c in cidades}

    eventos: list[EventoClimatico] = []
    for previsao in previsoes:
        cidade = por_chave.get((previsao.cidade, previsao.uf))
        oficiais = (
            inmet.alertas_da_cidade(alertas, cidade, previsao.inicio, previsao.fim)
            if cidade is not None
            else []
        )
        for evento in classificar(previsao, regras):
            if oficiais:
                evento = evento.model_copy(update={"alertas_oficiais": oficiais})
            eventos.append(evento)
    return eventos


def _decidir_notificacoes(
    segurados: Iterable[Segurado],
    eventos: Iterable[EventoClimatico],
    regras: Regras,
) -> list[DecisaoNotificar]:
    """Cruza eventos com segurados, consultando as regras de negócio.

    Um par evento × apólice sem recomendação em `regras.yaml` não notifica —
    é assim que "raio × automotiva" fica de fora sem precisar de exceção no
    código: o especialista simplesmente não escreveu recomendação para ele.
    """
    segurados = list(segurados)
    decisoes: list[DecisaoNotificar] = []

    for evento in eventos:
        for segurado in segurados:
            if (segurado.cidade, segurado.uf) != (evento.cidade, evento.uf):
                continue
            recomendacao = regras.recomendacao(evento.tipo, segurado.tipo_apolice)
            if recomendacao is None:
                continue
            decisoes.append(
                DecisaoNotificar(
                    segurado=segurado,
                    evento=evento,
                    regra_acionada=(
                        f"{evento.tipo.value} x {segurado.tipo_apolice.value}: {recomendacao}"
                    ),
                )
            )
    return decisoes


def processar_decisao(decisao: DecisaoNotificar) -> Notificacao:
    """Roda C.2 -> C.3 -> C.4 para uma única decisão.

    O fallback cobre os dois modos de falha da redação por LLM: a API não
    responder, e a mensagem responder mas não passar no guardrail.
    """
    try:
        notificacao = redator.redigir(decisao.segurado, decisao.evento, decisao.regra_acionada)
    except LLMIndisponivel as exc:
        log.info("redacao por LLM indisponivel (%s): usando template", exc)
        return fallback.gerar_fallback(decisao.segurado, decisao.evento, decisao.regra_acionada)

    ok, motivo = guardrails.validar_notificacao(notificacao)
    if not ok:
        log.warning("mensagem do LLM rejeitada pelo guardrail: %s", motivo)
        notificacao = fallback.gerar_fallback(
            decisao.segurado, decisao.evento, decisao.regra_acionada
        )
        notificacao.regra_acionada += f" (LLM rejeitado pelo guardrail: {motivo})"

    return notificacao


def rodar(
    segurados: list[Segurado], cidades: list[Cidade], regras: Regras | None = None
) -> list[Notificacao]:
    """Pipeline completo, da API à mensagem pronta para envio."""
    regras = regras or carregar_regras()
    eventos = _coletar_eventos(cidades, regras)
    decisoes = _decidir_notificacoes(segurados, eventos, regras)
    return [processar_decisao(d) for d in decisoes]


def rodar_com_eventos_mockados(
    segurados: list[Segurado],
    eventos: list[EventoClimatico],
    regras: Regras | None = None,
) -> list[Notificacao]:
    """Pula a coleta real — para testar C isoladamente e para a demonstração
    de cenário forçado, que não pode depender do tempo do dia."""
    regras = regras or carregar_regras()
    decisoes = _decidir_notificacoes(segurados, eventos, regras)
    return [processar_decisao(d) for d in decisoes]
