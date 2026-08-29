"""Testes do modo cenário forçado — tarefa D.2.

Nada toca a rede: os cenários fabricam PrevisaoHoraria e passam pelo mesmo
classificador da frente B. O que se avalia aqui é o compromisso central do D.2:
cada cenário, classificado com as regras oficiais, produz SEMPRE o evento e a
severidade pedidos.
"""

from __future__ import annotations

import pytest

from app.domain.cenarios import (
    CENARIOS_FORCADOS,
    FONTE_CENARIO,
    listar_cenarios,
    previsao_cenario,
)
from app.domain.eventos import classificar
from app.domain.regras import carregar_regras
from app.schemas import Cidade

CIDADE = Cidade(nome="Cidade Teste", uf="SP", latitude=-23.5, longitude=-46.6)
REGRAS = carregar_regras()


@pytest.mark.parametrize("nome", sorted(CENARIOS_FORCADOS))
def test_cenario_produz_o_evento_e_a_severidade_pedidos(nome: str) -> None:
    """Qualquer cenário de F0.1 pode ser disparado sob encomenda."""
    tipo_esperado, severidade_esperada = CENARIOS_FORCADOS[nome]

    eventos = classificar(previsao_cenario(nome, CIDADE), REGRAS)

    atingidos = {(e.tipo, e.severidade) for e in eventos}
    assert (tipo_esperado, severidade_esperada) in atingidos


def test_classificacao_e_deterministica() -> None:
    """A mesma previsão sempre produz a mesma classificação."""
    primeira = previsao_cenario("granizo", CIDADE).model_dump()
    segunda = previsao_cenario("granizo", CIDADE).model_dump()

    assert primeira == segunda
    assert primeira["fonte"] == FONTE_CENARIO


def test_janela_calma_nada_gera() -> None:
    """Sem extremos, silêncio: nenhum evento deve ser inventado."""
    from datetime import datetime, timedelta

    from app.domain.eventos import classificar as _classificar
    from app.schemas import PrevisaoHoraria

    base = datetime.now().replace(minute=0, second=0, microsecond=0)
    horas = [base + timedelta(hours=i) for i in range(24)]
    calma = PrevisaoHoraria(
        cidade=CIDADE.nome,
        uf=CIDADE.uf,
        horas=horas,
        precipitacao_mm=[1.0] * 24,
        rajada_km_h=[12.0] * 24,
        codigo_wmo=[1] * 24,
        cape_j_kg=[40.0] * 24,
        nivel_congelamento_m=[4200.0] * 24,
    )

    assert _classificar(calma, REGRAS) == []


def test_nome_de_cenario_desconhecido_falha_claramente() -> None:
    with pytest.raises(KeyError):
        previsao_cenario("meteoro", CIDADE)


def test_listar_cenarios_cobre_os_quatro_eventos() -> None:
    nomes = listar_cenarios()
    for tipo in ("chuva_intensa", "raio", "vento_forte", "granizo"):
        assert f"{tipo}" in nomes            # severidade ALERTA (curto)
        assert f"{tipo}_atencao" in nomes    # variante ATENCAO
