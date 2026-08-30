"""Orquestrador (C.1). Encadeia as quatro frentes numa passagem só:

    coleta (A) -> classificação e regras (B) -> redação (C) -> guardrail -> fallback

Este módulo é o **único caminho** para transformar um evento em mensagem. A
interface e o CLI da frente D chamam `gerar_notificacao()`; nada monta uma
`Notificacao` por fora. Sem essa regra o projeto ganhou, por um tempo, dois
pipelines paralelos — um com LLM e outro só com template — e a tela da
demonstração exibia "0 via LLM" porque não passava pelo redator.

Duas fronteiras importam aqui, e ambas apontam para a frente B como fonte de
verdade:

* **O que é um evento** vem de `domain.eventos.classificar()`, que aplica os
  limiares de `data/regras.yaml` — definidos pelo corretor do grupo, não por
  chute de quem programa.
* **Quem deve ser avisado, e do quê** vem de `Regras.recomendacao()`. A mesma
  chamada devolve a orientação preventiva que o especialista escreveu para
  aquele par evento × apólice, e é ela que viaja no `regra_acionada` até o
  prompt do redator e até o template.
"""

from __future__ import annotations

import logging
from typing import Iterable, NamedTuple

from ..clients import inmet, open_meteo
from ..domain.eventos import classificar
from ..domain.regras import Regras, carregar_regras
from ..schemas import Cidade, EventoClimatico, Notificacao, Segurado
from . import guardrails, redator, templates
from .llm import LLMIndisponivel

log = logging.getLogger(__name__)


class DecisaoNotificar(NamedTuple):
    """Este segurado deve ser avisado deste evento, por este motivo.

    `regra_acionada` carrega a versão das regras e a recomendação preventiva de
    `data/regras.yaml` — é o que dá conteúdo específico à mensagem e o que torna
    a decisão auditável depois, no registro da caixa de saída.
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
                        f"regras.yaml v{regras.versao} | {evento.tipo.value} x "
                        f"{segurado.tipo_apolice.value}: {recomendacao}"
                    ),
                )
            )
    return decisoes


def processar_decisao(
    decisao: DecisaoNotificar, regras: Regras, usar_llm: bool = True
) -> Notificacao:
    """Roda C.2 -> C.3 -> C.4 para uma única decisão.

    O template cobre os três modos de falha da redação por LLM: a API não
    responder, a mensagem responder mas não passar no guardrail, e o operador
    ter desligado o LLM para a demonstração não depender de cota.

    A mensagem por template nunca falha, então esta função sempre devolve uma
    `Notificacao` — a falha de uma não pode custar as outras na apresentação.
    """
    if usar_llm:
        try:
            notificacao = redator.redigir(
                decisao.segurado, decisao.evento, decisao.regra_acionada
            )
            aprovada, motivo = guardrails.validar_notificacao(notificacao)
            if aprovada:
                return notificacao
            log.warning("mensagem do LLM rejeitada pelo guardrail: %s", motivo)
            sufixo = f" (LLM rejeitado pelo guardrail: {motivo})"
        except LLMIndisponivel as exc:
            log.info("redacao por LLM indisponivel (%s): usando template", exc)
            sufixo = f" (LLM indisponivel: {exc})"
    else:
        sufixo = ""

    return _por_template(decisao, regras, sufixo)


def _por_template(decisao: DecisaoNotificar, regras: Regras, sufixo: str) -> Notificacao:
    """Redação determinística (C.4), com o mesmo `regra_acionada` do outro
    caminho — a origem da mensagem se lê em `gerada_por_llm`, não no rótulo da
    regra, para os dois caminhos serem comparáveis no relatório."""
    notificacao = templates.construir_notificacao(
        decisao.segurado, decisao.evento, regras
    )
    if notificacao is None:  # rede de segurança: a decisão já garantiu o par
        raise RuntimeError(
            f"template recusou um par que as regras aprovaram: "
            f"{decisao.evento.tipo.value} x {decisao.segurado.tipo_apolice.value}"
        )
    return notificacao.model_copy(
        update={"regra_acionada": decisao.regra_acionada + sufixo}
    )


def gerar_notificacao(
    segurado: Segurado,
    evento: EventoClimatico,
    regras: Regras,
    usar_llm: bool = True,
) -> Notificacao | None:
    """Mensagem deste segurado para este evento, ou `None` se as regras não
    mandam notificar esse par.

    É o ponto de entrada da frente D: interface e CLI passam por aqui, e por
    isso ganham o redator com LLM e o fallback pelo mesmo caminho.
    """
    decisoes = _decidir_notificacoes([segurado], [evento], regras)
    if not decisoes:
        return None
    return processar_decisao(decisoes[0], regras, usar_llm)


def rodar(
    segurados: list[Segurado],
    cidades: list[Cidade],
    regras: Regras | None = None,
    usar_llm: bool = True,
) -> list[Notificacao]:
    """Pipeline completo, da API à mensagem pronta para envio."""
    regras = regras or carregar_regras()
    eventos = _coletar_eventos(cidades, regras)
    decisoes = _decidir_notificacoes(segurados, eventos, regras)
    return [processar_decisao(d, regras, usar_llm) for d in decisoes]


def rodar_com_eventos_mockados(
    segurados: list[Segurado],
    eventos: list[EventoClimatico],
    regras: Regras | None = None,
    usar_llm: bool = True,
) -> list[Notificacao]:
    """Pula a coleta real — para testar C isoladamente e para a demonstração
    de cenário forçado, que não pode depender do tempo do dia."""
    regras = regras or carregar_regras()
    decisoes = _decidir_notificacoes(segurados, eventos, regras)
    return [processar_decisao(d, regras, usar_llm) for d in decisoes]
