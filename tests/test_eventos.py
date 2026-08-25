"""Testes do classificador de eventos e do carregador de regras (B.2 e B.3).

Nenhum destes testes toca a rede: a previsão é montada à mão, para que o
resultado dependa só dos limiares.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.eventos import classificar, classificar_varias
from app.domain.regras import Combinacao, ErroRegras, carregar_regras
from app.schemas import PrevisaoHoraria, Severidade, TipoApolice, TipoEvento

AGORA = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def regras():
    return carregar_regras()


def previsao(
    *,
    chuva: list[float | None] | None = None,
    rajada: list[float | None] | None = None,
    codigo: list[int | None] | None = None,
    cape: list[float | None] | None = None,
    congelamento: list[float | None] | None = None,
    horas: int | None = None,
) -> PrevisaoHoraria:
    """Monta uma previsão com valores calmos, exceto o que o teste informar.

    O número de horas vem da lista mais longa informada; as séries mais curtas
    são completadas com o valor calmo, para todas terminarem do mesmo tamanho.
    """
    informadas = [v for v in (chuva, rajada, codigo, cape, congelamento) if v is not None]
    n = horas or (max(len(v) for v in informadas) if informadas else 3)

    def serie(valores, padrao):
        if valores is None:
            return [padrao] * n
        return list(valores) + [padrao] * (n - len(valores))

    return PrevisaoHoraria(
        cidade="Cidade Teste",
        uf="SP",
        horas=[AGORA + timedelta(hours=i) for i in range(n)],
        precipitacao_mm=serie(chuva, 0.0),
        rajada_km_h=serie(rajada, 10.0),
        codigo_wmo=serie(codigo, 1),
        cape_j_kg=serie(cape, 50.0),
        nivel_congelamento_m=serie(congelamento, 4500.0),
    )


def tipos(eventos) -> set[TipoEvento]:
    return {e.tipo for e in eventos}


# ---------------------------------------------------------------------------
# Carga das regras
# ---------------------------------------------------------------------------


def test_regras_carregam_com_os_quatro_eventos(regras):
    assert set(regras.eventos) == set(TipoEvento)
    assert regras.definido_por == "Paulo Henrique"


def test_sete_cenarios_com_recomendacao(regras):
    assert len(regras.cenarios) == 7
    assert all(c.recomendacao for c in regras.cenarios)


def test_raio_nao_notifica_apolice_automotiva(regras):
    assert regras.notifica(TipoEvento.RAIO, TipoApolice.RESIDENCIAL)
    assert not regras.notifica(TipoEvento.RAIO, TipoApolice.AUTOMOTIVA)
    assert regras.recomendacao(TipoEvento.RAIO, TipoApolice.AUTOMOTIVA) is None


def test_combinacoes_conforme_definido(regras):
    assert regras.eventos[TipoEvento.CHUVA_INTENSA].combinacao is Combinacao.QUALQUER
    assert regras.eventos[TipoEvento.RAIO].combinacao is Combinacao.TODOS
    assert regras.eventos[TipoEvento.GRANIZO].combinacao is Combinacao.TODOS


def test_toda_justificativa_preenchida(regras):
    """A tarefa B.4 exige procedência de cada limiar."""
    for evento in regras.eventos.values():
        for criterio in evento.criterios:
            assert criterio.porque, f"{evento.tipo.value}/{criterio.medida} sem justificativa"


def test_medida_fora_do_contrato_e_recusada(tmp_path):
    arq = tmp_path / "r.yaml"
    arq.write_text(
        "eventos:\n  chuva_intensa:\n    criterios:\n"
        "      - medida: umidade_relativa\n        atencao: 80\n",
        encoding="utf-8",
    )
    with pytest.raises(ErroRegras, match="nao existe em Medidas"):
        carregar_regras(arq)


def test_cenario_sem_recomendacao_e_recusado(tmp_path):
    arq = tmp_path / "r.yaml"
    arq.write_text(
        "eventos:\n  vento_forte:\n    criterios:\n"
        "      - medida: rajada_km_h\n        atencao: 60\n"
        "cenarios:\n  - evento: vento_forte\n    apolice: residencial\n"
        "    recomendacao: ''\n",
        encoding="utf-8",
    )
    with pytest.raises(ErroRegras, match="sem recomendacao"):
        carregar_regras(arq)


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------


def test_tempo_calmo_nao_gera_evento(regras):
    """Silêncio é resposta correta — o caso da maioria das cidades."""
    assert classificar(previsao(), regras) == []


def test_chuva_acumulada_dispara_por_soma(regras):
    # 3 horas de 15 mm somam 45 mm: passa o limiar de 40 mm da janela
    eventos = classificar(previsao(chuva=[15.0, 15.0, 15.0]), regras)
    assert tipos(eventos) == {TipoEvento.CHUVA_INTENSA}
    assert eventos[0].medidas.precipitacao_mm_janela == 45.0


def test_chuva_horaria_forte_dispara_isolada(regras):
    # 16 mm numa hora só: acumulado fica abaixo de 40, mas a intensidade passa
    eventos = classificar(previsao(chuva=[16.0, 0.0, 0.0]), regras)
    assert tipos(eventos) == {TipoEvento.CHUVA_INTENSA}


def test_severidade_de_chuva_sobe_para_alerta(regras):
    atencao = classificar(previsao(chuva=[20.0, 20.0, 5.0]), regras)[0]   # 45 mm
    alerta = classificar(previsao(chuva=[30.0, 30.0, 5.0]), regras)[0]    # 65 mm
    assert atencao.severidade is Severidade.ATENCAO
    assert alerta.severidade is Severidade.ALERTA


def test_vento_nos_dois_patamares(regras):
    assert classificar(previsao(rajada=[65.0]), regras)[0].severidade is Severidade.ATENCAO
    assert classificar(previsao(rajada=[85.0]), regras)[0].severidade is Severidade.ALERTA
    assert classificar(previsao(rajada=[59.0]), regras) == []


def test_raio_exige_trovoada_e_energia(regras):
    # CAPE alto sozinho nao e raio: sem codigo de trovoada, nao classifica
    assert classificar(previsao(cape=[1200.0]), regras) == []
    # com trovoada prevista, classifica
    eventos = classificar(previsao(cape=[1200.0], codigo=[95]), regras)
    assert TipoEvento.RAIO in tipos(eventos)


def test_trovoada_sem_energia_nao_gera_raio(regras):
    assert classificar(previsao(codigo=[95], cape=[100.0]), regras) == []


def test_granizo_exige_congelamento_baixo(regras):
    # energia de sobra, mas isoterma alta: a pedra derrete antes de chegar
    quente = classificar(previsao(cape=[2000.0], codigo=[95], congelamento=[4500.0]), regras)
    assert TipoEvento.GRANIZO not in tipos(quente)
    # mesma energia com isoterma baixa: granizo entra
    frio = classificar(previsao(cape=[2000.0], codigo=[95], congelamento=[3000.0]), regras)
    assert TipoEvento.GRANIZO in tipos(frio)


def test_granizo_usa_a_condicao_mais_fraca(regras):
    """Energia em alerta mas congelamento só em atenção deve dar atenção."""
    eventos = classificar(
        previsao(cape=[2600.0], codigo=[95], congelamento=[3500.0]), regras
    )
    granizo = next(e for e in eventos if e.tipo is TipoEvento.GRANIZO)
    assert granizo.severidade is Severidade.ATENCAO


def test_granizo_em_alerta_quando_ambos_extremos(regras):
    eventos = classificar(
        previsao(cape=[2600.0], codigo=[95], congelamento=[3000.0]), regras
    )
    granizo = next(e for e in eventos if e.tipo is TipoEvento.GRANIZO)
    assert granizo.severidade is Severidade.ALERTA


def test_varios_eventos_na_mesma_cidade(regras):
    eventos = classificar(
        previsao(chuva=[35.0, 35.0], rajada=[90.0, 20.0], codigo=[95, 95],
                 cape=[2600.0, 100.0], congelamento=[3000.0, 4000.0], horas=2),
        regras,
    )
    assert {TipoEvento.CHUVA_INTENSA, TipoEvento.VENTO_FORTE,
            TipoEvento.RAIO, TipoEvento.GRANIZO} <= tipos(eventos)
    # mais graves primeiro
    assert eventos[0].severidade is Severidade.ALERTA


def test_evento_carrega_so_as_medidas_que_usou(regras):
    eventos = classificar(previsao(rajada=[90.0], chuva=[50.0]), regras)
    vento = next(e for e in eventos if e.tipo is TipoEvento.VENTO_FORTE)
    assert vento.medidas.rajada_km_h == 90.0
    # a chuva existia na previsao, mas nao pertence a este evento
    assert vento.medidas.precipitacao_mm_janela is None


def test_medida_ausente_nao_quebra(regras):
    """A API pode devolver a série incompleta."""
    p = previsao(rajada=[None, None, None], cape=[None, None, None])
    assert classificar(p, regras) == []


def test_classificacao_e_deterministica(regras):
    p = previsao(chuva=[20.0, 25.0], rajada=[70.0, 30.0], horas=2)
    a = classificar(p, regras)
    b = classificar(p, regras)
    assert [(e.tipo, e.severidade) for e in a] == [(e.tipo, e.severidade) for e in b]


def test_classificar_varias_agrega_cidades(regras):
    calma = previsao()
    ventosa = previsao(rajada=[95.0])
    eventos = classificar_varias([calma, ventosa], regras)
    assert len(eventos) == 1
    assert eventos[0].tipo is TipoEvento.VENTO_FORTE
