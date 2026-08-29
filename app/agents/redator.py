"""Agente Redator (C.2). Recebe um segurado, o evento que o atinge e a
regra que disparou a notificação, e devolve uma Notificacao com a
mensagem escrita pelo LLM no tom do canal/apólice.
"""

from __future__ import annotations

from datetime import datetime

from ..config import ConfigLLM
from ..schemas import (
    Canal,
    EventoClimatico,
    LIMITE_CARACTERES,
    Notificacao,
    Segurado,
    Severidade,
    StatusEnvio,
    TipoApolice,
)
from .llm import gerar_texto, LLMIndisponivel

TOM_POR_APOLICE = {
    TipoApolice.RESIDENCIAL: "acolhedor e protetor, focado na segurança da casa e da família",
    TipoApolice.AUTOMOTIVA: "direto e prático, focado em onde deixar o carro e cuidados imediatos",
}

URGENCIA_POR_SEVERIDADE = {
    Severidade.ATENCAO: "tom de atenção, sem alarmismo",
    Severidade.ALERTA: "tom de alerta, mais urgente, mas sem gerar pânico",
}


def _montar_prompt(segurado: Segurado, evento: EventoClimatico, regra_acionada: str) -> str:
    limite = LIMITE_CARACTERES[segurado.canal]
    tom = TOM_POR_APOLICE.get(segurado.tipo_apolice, "claro e profissional")
    urgencia = URGENCIA_POR_SEVERIDADE[evento.severidade]
    medidas_str = ", ".join(f"{k}={v}" for k, v in evento.medidas.preenchidas().items())

    return f"""Você é o redator de comunicação proativa de uma seguradora.
Escreva UMA mensagem de alerta para o segurado abaixo, em português do Brasil.

Segurado: {segurado.nome} ({segurado.tipo_apolice.value}, {segurado.local})
Canal: {segurado.canal.value} (limite de {limite} caracteres)
Evento previsto: {evento.tipo.value}, severidade {evento.severidade.value} ({urgencia})
Dados brutos disponíveis (só cite números que estejam aqui): {medidas_str}
Regra que disparou este aviso: {regra_acionada}
Tom desejado: {tom}

Regras obrigatórias:
- Cite no máximo os números que aparecem em "Dados brutos disponíveis". Não invente nenhum número.
- NÃO prometa cobertura, indenização ou reembolso. Você não decide sinistro.
- Seja específico sobre a ação recomendada.
- Respeite o limite de caracteres do canal.
- Não use saudação genérica de e-mail nem assinatura — só o corpo da mensagem.

Responda APENAS com o texto da mensagem, sem explicações."""


def redigir(
    segurado: Segurado,
    evento: EventoClimatico,
    regra_acionada: str,
    cfg: ConfigLLM | None = None,
) -> Notificacao:
    """Gera a Notificacao com mensagem escrita pelo LLM.

    Levanta LLMIndisponivel se nenhum modelo/provedor responder — quem
    chama (o orquestrador) deve capturar e cair no fallback (C.4).
    """
    prompt = _montar_prompt(segurado, evento, regra_acionada)
    mensagem = gerar_texto(prompt, cfg)

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
        gerada_por_llm=True,
    )
