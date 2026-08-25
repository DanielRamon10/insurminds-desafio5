"""Testes do cliente de alertas oficiais do INMET (A.4).

Sem rede: a resposta da API é simulada, inclusive nos formatos estranhos que ela
realmente devolve — os campos `riscos` e `instrucoes` chegam como a repr de uma
lista Python, não como JSON.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime

import pytest

from app.clients import inmet
from app.schemas import Cidade

CURITIBA = Cidade(
    nome="Curitiba", uf="PR", latitude=-25.43, longitude=-49.27, codigo_ibge="4106902"
)
MANAUS = Cidade(
    nome="Manaus", uf="AM", latitude=-3.12, longitude=-60.02, codigo_ibge="1302603"
)
SEM_CODIGO = Cidade(nome="Vila X", uf="SP", latitude=-23.0, longitude=-46.0)


def aviso(**campos) -> dict:
    """Aviso no formato real da API, com os campos que importam."""
    base = {
        "id": 55492,
        "id_aviso": 28121,
        "descricao": "Tempestade",
        "severidade": "Perigo Potencial",
        "inicio": "2026-08-26 00:00",
        "fim": "2026-08-26 23:59",
        "hora_inicio": "00:00",
        "hora_fim": "23:59",
        # a API devolve estes dois como repr de lista, entre aspas simples
        "riscos": "['Chuva entre 20 e 30 mm/h', 'Ventos intensos (40-60 km/h)']",
        "instrucoes": "['Nao se abrigue debaixo de arvores.', 'Desligue aparelhos.']",
        "geocodes": "4106902,4314902,3550308",
        "encerrado": False,
    }
    base.update(campos)
    return base


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(inmet, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(inmet, "ESPERA_INICIAL", 0.0)
    return tmp_path


def fingir_api(monkeypatch, retorno=None, erro=None, contador=None):
    def falso(url):
        if contador is not None:
            contador.append(url)
        if erro is not None:
            raise erro
        return retorno
    monkeypatch.setattr(inmet, "_baixar", falso)


# ---------------------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------------------


def test_le_avisos_de_hoje_e_do_futuro(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()], "futuro": [aviso(id_aviso=2)]})
    assert len(inmet.buscar_alertas()) == 2


def test_extrai_riscos_e_instrucoes_do_formato_repr(monkeypatch):
    """A API manda `['a', 'b']` como string, não como JSON."""
    fingir_api(monkeypatch, {"hoje": [aviso()]})
    a = inmet.buscar_alertas()[0]
    assert a.riscos == ["Chuva entre 20 e 30 mm/h", "Ventos intensos (40-60 km/h)"]
    assert a.instrucoes[0] == "Nao se abrigue debaixo de arvores."


def test_aceita_lista_de_verdade_tambem(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso(riscos=["Granizo"], instrucoes=["Recolha o carro"])]})
    a = inmet.buscar_alertas()[0]
    assert a.riscos == ["Granizo"]


def test_converte_janela_e_metadados(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()]})
    a = inmet.buscar_alertas()[0]
    assert a.titulo == "Tempestade"
    assert a.severidade == "Perigo Potencial"
    assert a.inicio == datetime(2026, 8, 26, 0, 0)
    assert a.fim == datetime(2026, 8, 26, 23, 59)
    assert a.codigos_ibge == {"4106902", "4314902", "3550308"}


def test_aviso_encerrado_e_ignorado(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso(encerrado=True), aviso(id_aviso=9)]})
    assert len(inmet.buscar_alertas()) == 1


def test_aviso_sem_janela_utilizavel_e_descartado(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso(inicio=None, fim=None)]})
    assert inmet.buscar_alertas() == []


def test_janela_invertida_e_descartada(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso(inicio="2026-08-26 20:00", fim="2026-08-26 08:00")]})
    assert inmet.buscar_alertas() == []


# ---------------------------------------------------------------------------
# Casamento por código IBGE
# ---------------------------------------------------------------------------


def test_casa_cidade_coberta_pelo_aviso(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()]})
    alertas = inmet.buscar_alertas()
    assert len(inmet.alertas_da_cidade(alertas, CURITIBA)) == 1


def test_cidade_fora_do_aviso_nao_casa(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()]})
    alertas = inmet.buscar_alertas()
    assert inmet.alertas_da_cidade(alertas, MANAUS) == []


def test_cidade_sem_codigo_ibge_nunca_casa(monkeypatch):
    """Sem código não há casamento — nome não serve, "Santos" casaria com
    "Santos Dumont"."""
    fingir_api(monkeypatch, {"hoje": [aviso(geocodes="3548500")]})
    alertas = inmet.buscar_alertas()
    assert inmet.alertas_da_cidade(alertas, SEM_CODIGO) == []


def test_filtra_por_sobreposicao_de_janela(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()]})  # aviso vale em 26/08
    alertas = inmet.buscar_alertas()

    # janela do dia 26: sobrepõe
    dentro = inmet.alertas_da_cidade(
        alertas, CURITIBA, datetime(2026, 8, 26, 12, 0), datetime(2026, 8, 27, 12, 0)
    )
    assert len(dentro) == 1

    # janela do dia 20: não sobrepõe
    fora = inmet.alertas_da_cidade(
        alertas, CURITIBA, datetime(2026, 8, 20, 0, 0), datetime(2026, 8, 21, 0, 0)
    )
    assert fora == []


def test_vigente_em_um_momento(monkeypatch):
    fingir_api(monkeypatch, {"hoje": [aviso()]})
    a = inmet.buscar_alertas()[0]
    assert a.vigente_em(datetime(2026, 8, 26, 10, 0))
    assert not a.vigente_em(datetime(2026, 8, 25, 10, 0))


# ---------------------------------------------------------------------------
# Cache e falhas
# ---------------------------------------------------------------------------


def test_uma_chamada_serve_para_todas_as_cidades(monkeypatch):
    chamadas: list[str] = []
    fingir_api(monkeypatch, {"hoje": [aviso()]}, contador=chamadas)
    inmet.buscar_alertas()
    inmet.buscar_alertas()
    assert len(chamadas) == 1  # segunda vem do cache


def test_falha_de_rede_nao_derruba_o_fluxo(monkeypatch):
    """A segunda fonte é reforço: sua ausência não pode interromper nada."""
    fingir_api(monkeypatch, erro=urllib.error.URLError("fora do ar"))
    assert inmet.buscar_alertas_tolerante() == []


def test_versao_estrita_levanta_erro(monkeypatch):
    fingir_api(monkeypatch, erro=urllib.error.URLError("fora do ar"))
    with pytest.raises(inmet.ErroAlertas):
        inmet.buscar_alertas()


def test_json_corrompido_e_tolerado(monkeypatch):
    fingir_api(monkeypatch, erro=json.JSONDecodeError("ruim", "", 0))
    assert inmet.buscar_alertas_tolerante() == []


def test_resposta_em_lista_simples_tambem_funciona(monkeypatch):
    """Formato alternativo: sem as chaves hoje/futuro."""
    fingir_api(monkeypatch, [aviso()])
    assert len(inmet.buscar_alertas()) == 1
