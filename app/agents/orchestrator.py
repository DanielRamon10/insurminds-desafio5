"""Orquestrador (C.1). Encadeia: coleta (Frente A) -> decisão/regras
(Frente B) -> redação (Frente C) -> guardrail -> fallback.

IMPORTANTE — ponta que ainda depende da Frente B:

O motor de regras ainda não tem uma classe própria em `schemas.py`
(provavelmente vai ler `data/regras.yaml`). `DecisaoNotificar` abaixo é
um placeholder local só para a Frente C não ficar bloqueada. Quando a
Frente B definir a interface real do motor de regras (B.3), troque
`_decidir_notificacoes()` pela chamada real; o resto do pipeline
(redator/guardrail/fallback) não muda.

A coleta (A.1-A.3) e o classificador (B.2) já estão plugados:
- `clients.open_meteo` e `clients.inmet` são os módulos reais da Frente A.
- `classificador_placeholder.classificar()` é meu placeholder para B.2 —
  troque pelo classificador real assim que a Frente B publicar, mantendo
  a assinatura `Medidas -> (TipoEvento, Severidade) | None`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, NamedTuple

from ..schemas import Cidade, EventoClimatico, Notificacao, Segurado, StatusEnvio
from . import fallback, guardrails, redator
from .classificador_placeholder import classificar
from .llm import LLMIndisponivel
from ..clients import inmet, open_meteo

log = logging.getLogger(__name__)


class DecisaoNotificar(NamedTuple):
    """Placeholder até a Frente B expor a interface real do motor de
    regras (B.3). Representa: este segurado deve ser notificado por
    causa deste evento, por este motivo."""

    segurado: Segurado
    evento: EventoClimatico
    regra_acionada: str


def _coletar_eventos(cidades: list[Cidade]) -> list[EventoClimatico]:
    """Coleta real: Open-Meteo (A.1-A.3) + enriquecimento com alertas do
    INMET (A.4). A classificação (que decide se a janela vira evento e
    com que severidade) ainda é o placeholder de B.2 — ver docstring do
    módulo."""
    previsoes, falhas = open_meteo.buscar_varias(cidades)
    for cidade, motivo in falhas:
        log.warning("sem previsao para %s: %s", cidade, motivo)

    alertas = inmet.buscar_alertas_tolerante()
    cidades_por_chave = {(c.nome, c.uf): c for c in cidades}

    eventos: list[EventoClimatico] = []
    for previsao in previsoes:
        medidas = previsao.agregar()
        classificacao = classificar(medidas)
        if classificacao is None:
            continue
        tipo, severidade = classificacao

        cidade_obj = cidades_por_chave.get((previsao.cidade, previsao.uf))
        alertas_da_cidade = (
            inmet.alertas_da_cidade(alertas, cidade_obj, previsao.inicio, previsao.fim)
            if cidade_obj is not None
            else []
        )

        eventos.append(
            EventoClimatico(
                cidade=previsao.cidade,
                uf=previsao.uf,
                tipo=tipo,
                severidade=severidade,
                inicio=previsao.inicio,
                fim=previsao.fim,
                medidas=medidas,
                alertas_oficiais=alertas_da_cidade,
            )
        )
    return eventos


def _decidir_notificacoes(
    segurados: Iterable[Segurado], eventos: Iterable[EventoClimatico]
) -> list[DecisaoNotificar]:
    """TODO(Frente B): substituir pela chamada real ao motor de regras
    (provavelmente em app/agents/domain/, lendo data/regras.yaml).
    Placeholder: usa EventoClimatico.atinge() (já existe em schemas.py)
    para não ficar bloqueado enquanto B.3 não chega."""
    decisoes = []
    for evento in eventos:
        for segurado in segurados:
            if segurado.cidade != evento.cidade or segurado.uf != evento.uf:
                continue
            if evento.atinge(segurado.tipo_apolice):
                decisoes.append(
                    DecisaoNotificar(
                        segurado=segurado,
                        evento=evento,
                        regra_acionada=f"[placeholder] {evento.tipo.value} x {segurado.tipo_apolice.value}",
                    )
                )
    return decisoes


def processar_decisao(decisao: DecisaoNotificar) -> Notificacao:
    """Roda C.2 -> C.3 -> C.4 para uma única decisão. Função exposta
    separadamente para poder ser testada/chamada isoladamente."""
    try:
        notificacao = redator.redigir(decisao.segurado, decisao.evento, decisao.regra_acionada)
    except LLMIndisponivel:
        return fallback.gerar_fallback(decisao.segurado, decisao.evento, decisao.regra_acionada)

    ok, motivo = guardrails.validar_notificacao(notificacao)
    if not ok:
        notificacao = fallback.gerar_fallback(decisao.segurado, decisao.evento, decisao.regra_acionada)
        notificacao.regra_acionada += f" (LLM rejeitado pelo guardrail: {motivo})"

    return notificacao


def rodar(segurados: list[Segurado], cidades: list[Cidade]) -> list[Notificacao]:
    eventos = _coletar_eventos(cidades)
    decisoes = _decidir_notificacoes(segurados, eventos)
    return [processar_decisao(d) for d in decisoes]


def rodar_com_eventos_mockados(
    segurados: list[Segurado], eventos: list[EventoClimatico]
) -> list[Notificacao]:
    """Pula a coleta real (A) — útil para testar C isoladamente ou na
    demo, sem depender da API/cliente estarem prontos."""
    decisoes = _decidir_notificacoes(segurados, eventos)
    return [processar_decisao(d) for d in decisoes]
