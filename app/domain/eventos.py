"""Classificador de eventos climáticos — tarefa B.2.

Transforma a série horária de uma cidade em eventos nomeados com severidade,
aplicando os limiares definidos pelo especialista em `data/regras.yaml`.

Duas propriedades importam aqui:

* **Determinismo.** A mesma previsão sempre produz a mesma classificação. Nada
  de aleatoriedade, nada de horário atual influenciando o resultado.
* **Rastreabilidade.** Cada evento carrega as medidas que o dispararam, então a
  mensagem pode citar valor real e o relatório pode auditar a decisão.
"""

from __future__ import annotations

import logging

from ..schemas import EventoClimatico, Medidas, PrevisaoHoraria, Severidade
from .regras import Combinacao, RegraEvento, Regras

log = logging.getLogger(__name__)

#: Ordem de gravidade, para escolher a severidade final de um evento.
_PESO = {Severidade.ATENCAO: 1, Severidade.ALERTA: 2}


def _severidade_do_evento(
    regra: RegraEvento, medidas: Medidas, codigos: set[int]
) -> Severidade | None:
    """Avalia todos os critérios e resolve a severidade do evento.

    Com `combinacao: todos`, um único critério não atingido descarta o evento —
    é o que impede CAPE alto sozinho de virar "raio" numa tarde de verão sem
    trovoada prevista. A severidade final é a **menor** entre os critérios: se a
    energia está em alerta mas o nível de congelamento só em atenção, o evento é
    atenção, porque a condição mais fraca limita o risco real.

    Com `combinacao: qualquer`, basta um critério, e vale a **maior** severidade
    atingida.
    """
    atingidas = [c.avaliar(medidas, codigos) for c in regra.criterios]

    if regra.combinacao is Combinacao.TODOS:
        if any(s is None for s in atingidas):
            return None
        # os critérios de lista (código WMO) confirmam ocorrência, não graduam:
        # deixá-los fora do mínimo evita que travem tudo em "atenção"
        graduaveis = [
            s for c, s in zip(regra.criterios, atingidas)
            if s is not None and not c.eh_lista
        ]
        if not graduaveis:
            return Severidade.ATENCAO
        return min(graduaveis, key=lambda s: _PESO[s])

    presentes = [s for s in atingidas if s is not None]
    if not presentes:
        return None
    return max(presentes, key=lambda s: _PESO[s])


def _medidas_relevantes(regra: RegraEvento, medidas: Medidas) -> Medidas:
    """Mantém apenas as medidas que este evento realmente usa.

    Evita que a mensagem sobre vento cite chuva só porque o número estava ali.
    """
    usadas = {c.medida for c in regra.criterios}
    return Medidas(**{campo: getattr(medidas, campo) for campo in usadas})


def classificar(previsao: PrevisaoHoraria, regras: Regras) -> list[EventoClimatico]:
    """Extrai os eventos presentes na janela de uma cidade.

    Devolve lista vazia quando nada atinge limiar — silêncio é resposta correta,
    e a maioria das cidades num dia comum cai nesse caso.
    """
    medidas = previsao.agregar()
    codigos = previsao.codigos_presentes()
    encontrados: list[EventoClimatico] = []

    for tipo, regra in regras.eventos.items():
        severidade = _severidade_do_evento(regra, medidas, codigos)
        if severidade is None:
            continue
        encontrados.append(
            EventoClimatico(
                cidade=previsao.cidade,
                uf=previsao.uf,
                tipo=tipo,
                severidade=severidade,
                inicio=previsao.inicio,
                fim=previsao.fim,
                medidas=_medidas_relevantes(regra, medidas),
                fonte=previsao.fonte,
            )
        )

    # mais graves primeiro, e nome como critério de desempate para a ordem ser estável
    encontrados.sort(key=lambda e: (-_PESO[e.severidade], e.tipo.value))
    if encontrados:
        log.info(
            "%s: %s",
            previsao.local,
            ", ".join(f"{e.tipo.value}/{e.severidade.value}" for e in encontrados),
        )
    return encontrados


def classificar_varias(
    previsoes: list[PrevisaoHoraria], regras: Regras
) -> list[EventoClimatico]:
    """Classifica várias cidades e devolve todos os eventos encontrados."""
    eventos: list[EventoClimatico] = []
    for previsao in previsoes:
        eventos.extend(classificar(previsao, regras))
    return eventos
