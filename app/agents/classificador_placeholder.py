"""Classificador de eventos — PLACEHOLDER até a Frente B entregar B.2.

Isto deveria morar em app/agents/domain/ e ter os limiares justificados
por B.4 (ver docs/ROTEIRO_DESAFIO5). Os números abaixo são um chute
razoável baseado na lógica de proxy descrita no roteiro (granizo não
vem pronto na API — deriva de CAPE elevado + trovoada + nível de
congelamento baixo), só para o pipeline rodar de ponta a ponta.

Troque por app.agents.domain.classificador (ou nome equivalente) assim
que a Frente B publicar o real — a assinatura (Medidas -> evento
classificado ou None) deve continuar igual para não quebrar o
orquestrador.
"""

from __future__ import annotations

from ..config import CODIGOS_TROVOADA
from ..schemas import Medidas, Severidade, TipoEvento


def classificar(medidas: Medidas) -> tuple[TipoEvento, Severidade] | None:
    """Devolve (tipo, severidade) se a janela caracteriza um evento, ou
    None se não há nada a notificar. Prioridade: granizo > raio > vento
    > chuva — eventos mais raros/graves checados primeiro.
    """
    trovoada = medidas.codigo_wmo in CODIGOS_TROVOADA if medidas.codigo_wmo is not None else False

    if (
        trovoada
        and (medidas.cape_j_kg or 0) >= 1000
        and medidas.nivel_congelamento_m is not None
        and medidas.nivel_congelamento_m <= 3500
    ):
        severidade = Severidade.ALERTA if (medidas.cape_j_kg or 0) >= 2000 else Severidade.ATENCAO
        return TipoEvento.GRANIZO, severidade

    if trovoada:
        severidade = Severidade.ALERTA if (medidas.cape_j_kg or 0) >= 1500 else Severidade.ATENCAO
        return TipoEvento.RAIO, severidade

    if (medidas.rajada_km_h or 0) >= 60:
        severidade = Severidade.ALERTA if medidas.rajada_km_h >= 80 else Severidade.ATENCAO
        return TipoEvento.VENTO_FORTE, severidade

    if (medidas.precipitacao_mm_janela or 0) >= 30:
        severidade = Severidade.ALERTA if medidas.precipitacao_mm_janela >= 50 else Severidade.ATENCAO
        return TipoEvento.CHUVA_INTENSA, severidade

    return None
