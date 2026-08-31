"""Testes da Frente C: guardrails (C.3) e troca de modelo em llm.py.

Cobre a fronteira que test_orquestrador.py não cobre: a validação da
mensagem em si (não o pipeline de decisão) e o comportamento de retry
do cliente de LLM. Nenhum teste toca a rede — o cliente de LLM é sempre
simulado via monkeypatch.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.agents import llm
from app.agents.guardrails import validar_notificacao
from app.schemas import (
    Canal,
    EventoClimatico,
    Medidas,
    Notificacao,
    Severidade,
    StatusEnvio,
    TipoApolice,
    TipoEvento,
)


def evento(medidas: Medidas | None = None) -> EventoClimatico:
    return EventoClimatico(
        cidade="Curitiba", uf="PR",
        tipo=TipoEvento.CHUVA_INTENSA, severidade=Severidade.ALERTA,
        inicio=datetime(2026, 8, 29, 0, 0), fim=datetime(2026, 8, 30, 0, 0),
        medidas=medidas or Medidas(precipitacao_mm_janela=81.0, precipitacao_mm_h=35.0),
    )


def notificacao(mensagem: str, canal: Canal = Canal.SMS, ev: EventoClimatico | None = None) -> Notificacao:
    return Notificacao(
        segurado_id="S1", segurado_nome="Ana", tipo_apolice=TipoApolice.RESIDENCIAL,
        evento=ev or evento(), canal=canal, mensagem=mensagem,
        regra_acionada="teste", gerada_em=datetime.now(),
        status=StatusEnvio.PENDENTE, gerada_por_llm=True,
    )


# ---------------------------------------------------------------------------
# Guardrails (C.3)
# ---------------------------------------------------------------------------


def test_guardrail_rejeita_numero_inventado():
    n = notificacao("Risco de 90 por cento de chuva, fique atento.")
    ok, motivo = validar_notificacao(n)
    assert not ok
    assert "90" in motivo


def test_guardrail_rejeita_promessa_cobertura():
    n = notificacao("Fique tranquilo, sua cobertura está garantida.")
    ok, motivo = validar_notificacao(n)
    assert not ok
    assert "cobertura" in motivo


def test_guardrail_aceita_referencia_de_tempo_como_24_horas():
    """Bug real: '24 horas' era rejeitado por não ser nenhuma medida do
    evento, embora seja um prazo, não um dado climático inventado."""
    n = notificacao("Chuva de 35mm/h prevista nas próximas 24 horas.")
    ok, motivo = validar_notificacao(n)
    assert ok, motivo


def test_guardrail_aceita_mensagem_com_numero_real_da_medida():
    n = notificacao("Chuva de 35mm/h prevista, verifique calhas e ralos.")
    ok, motivo = validar_notificacao(n)
    assert ok, motivo


def test_guardrail_rejeita_mensagem_que_estoura_limite_do_canal():
    n = notificacao("x" * 200, canal=Canal.SMS)  # limite SMS é 160
    ok, motivo = validar_notificacao(n)
    assert not ok
    assert "limite" in motivo


# ---------------------------------------------------------------------------
# llm.py — troca de modelo (nenhum teste toca a rede de verdade)
# ---------------------------------------------------------------------------


def test_llm_troca_de_modelo_quando_cota_estoura(monkeypatch):
    monkeypatch.setattr(llm, "_rede_marcada_indisponivel", False)
    monkeypatch.setattr(llm, "obter_api_key", lambda provedor: "chave-fake")

    modelos_tentados: list[str] = []

    class ChatFake:
        def __init__(self, modelo: str):
            self.modelo = modelo

        def invoke(self, prompt: str):
            modelos_tentados.append(self.modelo)
            if len(modelos_tentados) == 1:
                raise RuntimeError("429 Resource exhausted: cota diaria estourada")

            class Resposta:
                content = "mensagem gerada pelo segundo modelo"

            return Resposta()

    monkeypatch.setattr(
        llm, "_montar_chat_model", lambda provedor, modelo, api_key: ChatFake(modelo)
    )

    texto = llm.gerar_texto("prompt de teste")

    assert texto == "mensagem gerada pelo segundo modelo"
    assert len(modelos_tentados) == 2
    assert modelos_tentados[0] != modelos_tentados[1]  # tentou modelos diferentes

# ---------------------------------------------------------------------------
# llm.py — formato da resposta do modelo
#
# Regressão: o Gemini devolve `content` como lista de blocos quando o modelo usa
# "thinking". Um `.strip()` direto nessa lista levanta AttributeError, que o
# `except Exception` do laço de modelos tratava como "este modelo falhou" — então
# todos os modelos "falhavam" em sequência e o pipeline caía no template com a
# chave funcionando perfeitamente. O bug se disfarçava de fallback correto.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "conteudo, esperado",
    [
        ("Chuva a caminho.", "Chuva a caminho."),
        (["Chuva ", "a caminho."], "Chuva a caminho."),
        ([{"type": "text", "text": "Chuva a caminho."}], "Chuva a caminho."),
        ([{"content": "Chuva a caminho."}], "Chuva a caminho."),
        (
            [
                {"type": "thinking", "thinking": "o segurado tem apolice residencial"},
                {"type": "text", "text": "Chuva a caminho."},
            ],
            "Chuva a caminho.",
        ),
        ("  Chuva a caminho.  ", "Chuva a caminho."),
        (None, ""),
        ([], ""),
    ],
)
def test_extrai_texto_de_todos_os_formatos_de_resposta(conteudo, esperado):
    assert llm._extrair_texto(conteudo) == esperado


def test_resposta_em_blocos_nao_derruba_a_geracao(monkeypatch):
    """O caminho completo: resposta em lista chega ao `gerar_texto` e sai texto,
    em vez de virar falha de modelo."""
    monkeypatch.setattr(llm, "_rede_marcada_indisponivel", False)
    monkeypatch.setattr(llm, "obter_api_key", lambda provedor: "chave-fake")

    class ChatFake:
        def invoke(self, prompt: str):
            class Resposta:
                content = [
                    {"type": "thinking", "thinking": "pensando"},
                    {"type": "text", "text": "Chuva intensa prevista para hoje."},
                ]

            return Resposta()

    monkeypatch.setattr(
        llm, "_montar_chat_model", lambda provedor, modelo, api_key: ChatFake()
    )

    assert llm.gerar_texto("prompt") == "Chuva intensa prevista para hoje."
