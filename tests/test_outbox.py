"""Testes da caixa de saída simulada — tarefa D.1.

O foco é o registro auditável: cada notificação sai com destinatário, canal,
evento, mensagem, timestamp e status; estouro de limite do canal vira descarte.
Nenhum teste usa o diretório `data/` real.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.outbox import CaixaDeSaida, ler_registros
from app.schemas import Canal, EventoClimatico, LIMITE_CARACTERES, Medidas, Notificacao


@pytest.fixture
def evento() -> EventoClimatico:
    agora = datetime(2026, 9, 1, 12, 0, 0)
    return EventoClimatico(
        cidade="Porto Alegre",
        uf="RS",
        tipo="granizo",
        severidade="alerta",
        inicio=agora,
        fim=agora.replace(hour=13),
        medidas=Medidas(cape_j_kg=2800.0, nivel_congelamento_m=2600.0),
        fonte="cenario-forcado",
    )


def notificacao(evento: EventoClimatico, mensagem: str = "recorra a cobertura") -> Notificacao:
    return Notificacao(
        segurado_id="SEG-001",
        segurado_nome="Simone Carvalho Reis",
        tipo_apolice="automotiva",
        evento=evento,
        canal="sms",
        mensagem=mensagem,
        regra_acionada="regras.yaml v1: granizo/alerta",
        gerada_em=datetime.now(),
        status="pendente",
        gerada_por_llm=False,
    )


def test_registrar_salva_registro_auditavel(tmp_path, evento) -> None:
    caixa = CaixaDeSaida(diretorio=tmp_path)
    final = caixa.registrar(notificacao(evento))

    registros = ler_registros(caixa.arquivo)
    assert len(registros) == 1
    registro = registros[0]
    assert registro["segurado_id"] == "SEG-001"
    assert registro["canal"] == "sms"
    assert registro["status"] == "simulado"
    assert registro["registrado_em"]
    # o evento viaja inteiro dentro do registro, para auditoria
    assert registro["evento"]["tipo"] == "granizo"


def test_estouro_de_limite_do_canal_vira_descartado(tmp_path, evento) -> None:
    grande = "x" * (LIMITE_CARACTERES[Canal.SMS] + 10)
    caixa = CaixaDeSaida(diretorio=tmp_path)

    final = caixa.registrar(notificacao(evento, mensagem=grande))

    assert final.status.value == "descartado"
    assert ler_registros(caixa.arquivo)[0]["status"] == "descartado"


def test_lotes_sao_arquivos_separados(tmp_path, evento) -> None:
    caixa = CaixaDeSaida(diretorio=tmp_path)
    primeiro = caixa.iniciar_lote()
    caixa.registrar(notificacao(evento))
    segundo = caixa.iniciar_lote()
    caixa.registrar(notificacao(evento))

    assert primeiro != segundo
    assert len(ler_registros(primeiro)) == 1
    assert len(ler_registros(segundo)) == 1


def test_carregar_lote_sem_nenhum_registro(tmp_path) -> None:
    caixa = CaixaDeSaida(diretorio=tmp_path)
    assert caixa.carregar_lote() == []
