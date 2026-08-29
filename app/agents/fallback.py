"""Fallback sem LLM (C.4). Usado quando todos os modelos/provedores
configurados falharem, ou quando o guardrail rejeitar a mensagem do LLM.
"""

from __future__ import annotations

from datetime import datetime

from ..schemas import EventoClimatico, Notificacao, Segurado, StatusEnvio, TipoEvento

TEMPLATES = {
    TipoEvento.CHUVA_INTENSA: (
        "Alerta: previsão de chuva intensa em {local}"
        "{precipitacao}. Verifique calhas e ralos da sua propriedade "
        "nas próximas horas."
    ),
    TipoEvento.RAIO: (
        "Alerta: risco de raios em {local} nas próximas horas. "
        "Evite áreas abertas e desligue aparelhos eletrônicos sensíveis."
    ),
    TipoEvento.VENTO_FORTE: (
        "Alerta: rajadas de vento{rajada} previstas para {local}. "
        "Evite deixar o veículo sob árvores ou estruturas soltas."
    ),
    TipoEvento.GRANIZO: (
        "Alerta: condições favoráveis a granizo em {local}. "
        "Se possível, guarde seu veículo em local coberto."
    ),
}


def _formatar_medidas(evento: EventoClimatico) -> dict[str, str]:
    m = evento.medidas
    precipitacao = (
        f" ({m.precipitacao_mm_janela}mm acumulados)" if m.precipitacao_mm_janela else ""
    )
    rajada = f" de até {m.rajada_km_h}km/h" if m.rajada_km_h else ""
    return {"precipitacao": precipitacao, "rajada": rajada}


def gerar_fallback(segurado: Segurado, evento: EventoClimatico, regra_acionada: str) -> Notificacao:
    template = TEMPLATES.get(
        evento.tipo,
        "Alerta: evento climático ({tipo}) previsto para {local}. Recomendamos atenção redobrada.",
    )
    extras = _formatar_medidas(evento)
    mensagem = template.format(local=evento.local, tipo=evento.tipo.value, **extras)

    return Notificacao(
        segurado_id=segurado.id,
        segurado_nome=segurado.nome,
        tipo_apolice=segurado.tipo_apolice,
        evento=evento,
        canal=segurado.canal,
        mensagem=mensagem,
        regra_acionada=regra_acionada,
        gerada_em=datetime.now(),
        status=StatusEnvio.PENDENTE,
        gerada_por_llm=False,
    )
