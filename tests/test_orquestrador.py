"""Testes da integração entre as frentes B e C (orquestrador).

O foco é a fronteira: se o orquestrador realmente obedece a `data/regras.yaml`
— os limiares e os pares evento × apólice do corretor — em vez de decidir por
conta própria. A redação por LLM é sempre simulada: nenhum teste toca a rede.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.agents import orchestrator
from app.agents.llm import LLMIndisponivel
from app.domain.eventos import classificar
from app.domain.regras import carregar_regras
from app.schemas import (
    AlertaOficial,
    Canal,
    Cidade,
    PrevisaoHoraria,
    Segurado,
    TipoApolice,
    TipoEvento,
)

REGRAS = carregar_regras()

CURITIBA = Cidade(
    nome="Curitiba", uf="PR", latitude=-25.43, longitude=-49.27, codigo_ibge="4106902"
)


def segurado(apolice=TipoApolice.RESIDENCIAL, cidade="Curitiba", uf="PR") -> Segurado:
    return Segurado(
        id="S1", nome="Ana", tipo_apolice=apolice, cidade=cidade, uf=uf,
        latitude=-25.43, longitude=-49.27, canal=Canal.SMS,
    )


def previsao(chuva_h=0.0, rajada=10.0, wmo=1, cape=40.0, congelamento=4200.0, horas=24):
    inicio = datetime(2026, 8, 29, 0, 0)
    return PrevisaoHoraria(
        cidade="Curitiba", uf="PR",
        horas=[inicio + timedelta(hours=i) for i in range(horas)],
        precipitacao_mm=[chuva_h] * horas,
        rajada_km_h=[rajada] * horas,
        codigo_wmo=[wmo] * horas,
        cape_j_kg=[cape] * horas,
        nivel_congelamento_m=[congelamento] * horas,
    )


def aviso_inmet() -> AlertaOficial:
    return AlertaOficial(
        id="1", titulo="Tempestade", severidade="Perigo",
        inicio=datetime(2026, 8, 29, 0, 0), fim=datetime(2026, 8, 30, 0, 0),
        codigos_ibge={"4106902"},
    )


@pytest.fixture(autouse=True)
def llm_simulado(monkeypatch):
    """Redação previsível, sem rede. Quem testa o fallback sobrescreve."""
    monkeypatch.setattr(
        orchestrator.redator, "gerar_texto", lambda prompt, cfg=None: "Chuva a caminho."
    )


def coletar(monkeypatch, previsoes, alertas=None):
    monkeypatch.setattr(
        orchestrator.open_meteo, "buscar_varias", lambda cidades, *a, **k: (previsoes, [])
    )
    monkeypatch.setattr(
        orchestrator.inmet, "buscar_alertas_tolerante", lambda *a, **k: alertas or []
    )
    return orchestrator._coletar_eventos([CURITIBA], REGRAS)


# ---------------------------------------------------------------------------
# Os limiares que valem são os do especialista, não os do código
# ---------------------------------------------------------------------------


def test_abaixo_do_limiar_do_especialista_nao_vira_evento(monkeypatch):
    """35 mm em 24 h fica abaixo do limiar de atenção (40 mm) de regras.yaml.
    O placeholder anterior usava 30 mm e notificava neste caso."""
    assert coletar(monkeypatch, [previsao(chuva_h=35 / 24)]) == []


def test_acima_do_limiar_vira_evento(monkeypatch):
    eventos = coletar(monkeypatch, [previsao(chuva_h=45 / 24)])
    assert [e.tipo for e in eventos] == [TipoEvento.CHUVA_INTENSA]


def test_uma_janela_pode_render_mais_de_um_evento(monkeypatch):
    """Trovoada forte com nível de congelamento baixo é raio e granizo ao mesmo
    tempo — o classificador real não escolhe um só, como o placeholder fazia."""
    eventos = coletar(monkeypatch, [previsao(wmo=95, cape=2600.0, congelamento=3100.0)])
    assert {e.tipo for e in eventos} == {TipoEvento.RAIO, TipoEvento.GRANIZO}


# ---------------------------------------------------------------------------
# Quem é notificado sai de regras.yaml
# ---------------------------------------------------------------------------


def test_par_sem_recomendacao_no_yaml_nao_notifica():
    """Raio × automotiva não tem recomendação: o carro é gaiola de Faraday.
    A ausência no YAML é a regra — não há exceção escrita no código."""
    raios = [e for e in classificar(previsao(wmo=95, cape=1000.0), REGRAS)
             if e.tipo is TipoEvento.RAIO]
    assert raios, "o cenario de teste deveria produzir raio"

    decisoes = orchestrator._decidir_notificacoes(
        [segurado(TipoApolice.AUTOMOTIVA)], raios, REGRAS
    )
    assert decisoes == []


def test_mesmo_evento_notifica_a_apolice_prevista():
    raios = [e for e in classificar(previsao(wmo=95, cape=1000.0), REGRAS)
             if e.tipo is TipoEvento.RAIO]
    decisoes = orchestrator._decidir_notificacoes(
        [segurado(TipoApolice.RESIDENCIAL)], raios, REGRAS
    )
    assert len(decisoes) == 1


def test_recomendacao_do_especialista_chega_na_regra_acionada():
    """É esta string que vai para o prompt do redator; se ela não carregar a
    orientação do YAML, a mensagem sai genérica."""
    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    decisoes = orchestrator._decidir_notificacoes([segurado()], eventos, REGRAS)

    esperada = REGRAS.recomendacao(TipoEvento.CHUVA_INTENSA, TipoApolice.RESIDENCIAL)
    assert esperada and esperada in decisoes[0].regra_acionada


def test_segurado_de_outra_cidade_nao_e_notificado():
    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    outro = segurado(cidade="Manaus", uf="AM")
    assert orchestrator._decidir_notificacoes([outro], eventos, REGRAS) == []


# ---------------------------------------------------------------------------
# INMET enriquece, não decide (A.4)
# ---------------------------------------------------------------------------


def test_alerta_oficial_anexa_ao_evento_sem_criar_outro(monkeypatch):
    eventos = coletar(monkeypatch, [previsao(chuva_h=45 / 24)], alertas=[aviso_inmet()])
    assert len(eventos) == 1
    assert [a.titulo for a in eventos[0].alertas_oficiais] == ["Tempestade"]


def test_alerta_oficial_sozinho_nao_cria_evento(monkeypatch):
    """Céu calmo com aviso oficial vigente continua sem evento: um único aviso
    do INMET chega a cobrir quase dois mil municípios."""
    assert coletar(monkeypatch, [previsao()], alertas=[aviso_inmet()]) == []


# ---------------------------------------------------------------------------
# Redação e fallback
# ---------------------------------------------------------------------------


def test_pipeline_completo_gera_notificacao(monkeypatch):
    monkeypatch.setattr(
        orchestrator.open_meteo,
        "buscar_varias",
        lambda cidades, *a, **k: ([previsao(chuva_h=45 / 24)], []),
    )
    monkeypatch.setattr(orchestrator.inmet, "buscar_alertas_tolerante", lambda *a, **k: [])

    notificacoes = orchestrator.rodar([segurado()], [CURITIBA], REGRAS)
    assert len(notificacoes) == 1
    assert notificacoes[0].gerada_por_llm is True


def test_llm_indisponivel_cai_no_template(monkeypatch):
    def explode(prompt, cfg=None):
        raise LLMIndisponivel("cota estourada")

    monkeypatch.setattr(orchestrator.redator, "gerar_texto", explode)

    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    notificacoes = orchestrator.rodar_com_eventos_mockados([segurado()], eventos, REGRAS)

    assert len(notificacoes) == 1
    assert notificacoes[0].gerada_por_llm is False
    assert notificacoes[0].mensagem


def test_llm_desligado_nao_chama_o_redator(monkeypatch):
    """`usar_llm=False` é o modo da apresentação sem cota: nem tenta a rede."""
    def nao_deveria(prompt, cfg=None):
        raise AssertionError("o redator foi chamado com o LLM desligado")

    monkeypatch.setattr(orchestrator.redator, "gerar_texto", nao_deveria)

    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    notificacoes = orchestrator.rodar_com_eventos_mockados(
        [segurado()], eventos, REGRAS, usar_llm=False
    )
    assert len(notificacoes) == 1
    assert notificacoes[0].gerada_por_llm is False


def test_template_fala_de_carro_para_apolice_automotiva():
    """O template escolhe a orientação pelo par evento × apólice. Antes da
    consolidação o dono do carro ouvia "verifique calhas e ralos"."""
    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    notificacao = orchestrator.gerar_notificacao(
        segurado(TipoApolice.AUTOMOTIVA), eventos[0], REGRAS, usar_llm=False
    )
    esperada = REGRAS.recomendacao(TipoEvento.CHUVA_INTENSA, TipoApolice.AUTOMOTIVA)
    assert esperada
    # a recomendação pode vir cortada no limite do canal; o começo tem de bater
    assert esperada[:40] in notificacao.mensagem


def test_gerar_notificacao_respeita_a_matriz_de_negocio():
    """O ponto de entrada da frente D obedece às mesmas regras do pipeline."""
    raios = [e for e in classificar(previsao(wmo=95, cape=1000.0), REGRAS)
             if e.tipo is TipoEvento.RAIO]
    assert orchestrator.gerar_notificacao(
        segurado(TipoApolice.AUTOMOTIVA), raios[0], REGRAS, usar_llm=False
    ) is None
    assert orchestrator.gerar_notificacao(
        segurado(TipoApolice.RESIDENCIAL), raios[0], REGRAS, usar_llm=False
    ) is not None


def test_mensagem_cabe_no_canal_em_todos_os_cenarios():
    """A caixa de saída descarta o que estoura o limite; nenhuma combinação de
    evento × apólice × canal pode chegar lá estourada."""
    from app.schemas import LIMITE_CARACTERES

    for cenario in [previsao(chuva_h=60 / 24, rajada=95.0),
                    previsao(wmo=95, cape=2800.0, congelamento=2600.0)]:
        for evento in classificar(cenario, REGRAS):
            for apolice in TipoApolice:
                for canal in Canal:
                    s = segurado(apolice).model_copy(update={"canal": canal})
                    n = orchestrator.gerar_notificacao(s, evento, REGRAS, usar_llm=False)
                    if n is None:
                        continue
                    assert len(n.mensagem) <= LIMITE_CARACTERES[canal], (
                        f"{evento.tipo.value}/{apolice.value}/{canal.value}: "
                        f"{len(n.mensagem)} caracteres"
                    )


def test_uma_falha_de_llm_nao_derruba_as_outras_notificacoes(monkeypatch):
    """O fallback é por notificação: uma mensagem que falha não pode custar as
    demais na hora da apresentação."""
    chamadas = {"n": 0}

    def as_vezes(prompt, cfg=None):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise LLMIndisponivel("a primeira falhou")
        return "Chuva a caminho."

    monkeypatch.setattr(orchestrator.redator, "gerar_texto", as_vezes)

    eventos = classificar(previsao(chuva_h=45 / 24), REGRAS)
    dois = [segurado(), segurado(TipoApolice.AUTOMOTIVA)]
    notificacoes = orchestrator.rodar_com_eventos_mockados(dois, eventos, REGRAS)

    assert len(notificacoes) == 2
    assert {n.gerada_por_llm for n in notificacoes} == {False, True}
