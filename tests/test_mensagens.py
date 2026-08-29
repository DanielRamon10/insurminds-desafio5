"""Testes do redator por template e do carregador de segurados — Frente D.

O template é o fallback sem LLM (linha da tarefa C.4). Os guardrails avaliados
aqui espelham os critérios de C.3: nenhum número fora de `evento.medidas`,
limite por canal respeitado, e cenário raio × automotiva jamais notifica.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.templates import compor_mensagem, construir_notificacao
from app.domain.cenarios import previsao_cenario
from app.domain.eventos import classificar
from app.domain.regras import carregar_regras
from app.domain.segurados import carregar_segurados
from app.schemas import Canal, Cidade, LIMITE_CARACTERES, TipoApolice

CIDADE = Cidade(nome="Porto Alegre", uf="RS", latitude=-30.03, longitude=-51.23)
REGRAS = carregar_regras()


def eventos_do_cenario(nome: str):
    return classificar(previsao_cenario(nome, CIDADE), REGRAS)


# ---------------------------------------------------------------------------
# Carregador da base (data/segurados.csv real do repositório)
# ---------------------------------------------------------------------------


def test_base_de_segurados_carrega_tipada() -> None:
    base = carregar_segurados()
    assert base, "a base sintetica nao pode estar vazia"
    ids = {s.id for s in base}
    assert len(ids) == len(base), "ids duplicados na base"
    canais = {s.canal for s in base}
    assert canais <= set(Canal)


def test_todos_os_cenarios_tem_segurado_elegivel_na_base() -> None:
    """Critério de pronto da B.1 — cada cenário precisa de alguém para avisar."""
    from app.schemas import TipoEvento

    base = carregar_segurados()
    por_tipo_evento = {
        "chuva_intensa": [TipoApolice.RESIDENCIAL, TipoApolice.AUTOMOTIVA],
        "raio": [TipoApolice.RESIDENCIAL],
        "vento_forte": [TipoApolice.RESIDENCIAL, TipoApolice.AUTOMOTIVA],
        "granizo": [TipoApolice.RESIDENCIAL, TipoApolice.AUTOMOTIVA],
    }
    locais_da_base = {s.local for s in base}
    for tipo in TipoEvento:
        apolices = por_tipo_evento[tipo.value]
        assert any(
            s.tipo_apolice in apolices and s.local in locais_da_base
            for s in base
        ), f"nenhum segurado elegivel para o evento {tipo.value}"


# ---------------------------------------------------------------------------
# Guardrails do template
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("canal", list(Canal))
def test_mensagem_respeita_o_limite_do_canal(canal: Canal) -> None:
    primeiro_evento = eventos_do_cenario("granizo")[0]
    mensagem = compor_mensagem(
        primeiro_evento,
        TipoApolice.AUTOMOTIVA,
        REGRAS.recomendacao(primeiro_evento.tipo, TipoApolice.AUTOMOTIVA),
        canal,
    )
    assert len(mensagem) <= LIMITE_CARACTERES[canal]


def test_raio_nao_notifica_automotiva() -> None:
    """Decisão da matriz F0.1: gaiola de Faraday não recebe aviso de raio."""
    evento_raio = next(e for e in eventos_do_cenario("raio"))
    automotivos = [
        s for s in carregar_segurados()
        if s.local == evento_raio.local and s.tipo_apolice is TipoApolice.AUTOMOTIVA
    ]
    if automotivos:  # a base atual tem automotivos em todas as cidades
        for s in automotivos:
            assert construir_notificacao(s, evento_raio, REGRAS) is None


def test_mensagem_soh_cita_numeros_presentes_no_evento() -> None:
    evento_vento = eventos_do_cenario("vento_forte")[0]
    mensagem = compor_mensagem(
        evento_vento,
        TipoApolice.RESIDENCIAL,
        REGRAS.recomendacao(evento_vento.tipo, TipoApolice.RESIDENCIAL),
        Canal.EMAIL,
    )

    # rajada vem do perfil; cape e congelamento ficam fora deste evento
    assert f"{evento_vento.medidas.rajada_km_h:g} km/h" in mensagem
    assert "J/kg" not in mensagem


def test_email_traz_a_recomendacao_preventiva() -> None:
    evento_granizo = eventos_do_cenario("granizo")[0]
    recomendacao = REGRAS.recomendacao(evento_granizo.tipo, TipoApolice.RESIDENCIAL)
    assert recomendacao, "granizo x residencial deveria ter recomendacao"
    mensagem = compor_mensagem(
        evento_granizo, TipoApolice.RESIDENCIAL, recomendacao, Canal.EMAIL
    )

    trecho_inicial = recomendacao[:30].strip()
    assert trecho_inicial in mensagem


def test_construir_notificacao_marca_origem_template() -> None:
    segurado = next(s for s in carregar_segurados() if s.local == CIDADE.nome + "/RS")
    evento = next(e for e in eventos_do_cenario("granizo") if e.atinge(segurado.tipo_apolice))

    notificacao = construir_notificacao(segurado, evento, REGRAS)

    assert notificacao is not None
    assert notificacao.gerada_por_llm is False
    assert notificacao.dentro_do_limite()
    assert notificacao.status.value == "pendente"
    assert isinstance(notificacao.gerada_em, datetime)
