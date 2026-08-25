"""Testes do cliente da Open-Meteo (A.1 e A.2).

Nenhum teste toca a rede: a resposta da API é simulada. O foco é a tolerância a
falha — cache, novas tentativas e o último recurso do cache vencido.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime

import pytest

from app.clients import open_meteo
from app.schemas import Cidade

CIDADE = Cidade(nome="Cidade Teste", uf="SP", latitude=-23.5, longitude=-46.6)


def resposta(horas: int = 3, **series) -> dict:
    """Resposta da API no formato real, com valores calmos por padrão."""
    base = {
        "time": [f"2026-08-25T{h:02d}:00" for h in range(horas)],
        "precipitation": [0.0] * horas,
        "wind_gusts_10m": [12.0] * horas,
        "weather_code": [1] * horas,
        "cape": [40.0] * horas,
        "freezing_level_height": [4200.0] * horas,
    }
    base.update(series)
    return {"hourly": base}


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    """Cada teste usa um cache próprio, para não herdar estado."""
    monkeypatch.setattr(open_meteo, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(open_meteo, "ESPERA_INICIAL", 0.0)  # sem espera nos testes
    return tmp_path


def fingir_api(monkeypatch, retorno=None, erro=None, contador=None):
    def falso(url):
        if contador is not None:
            contador.append(url)
        if erro is not None:
            raise erro
        return retorno
    monkeypatch.setattr(open_meteo, "_baixar", falso)


# ---------------------------------------------------------------------------
# A.1 — conversão
# ---------------------------------------------------------------------------


def test_converte_resposta_para_o_contrato(monkeypatch):
    fingir_api(monkeypatch, resposta(horas=3))
    p = open_meteo.buscar_previsao(CIDADE, horas=3)
    assert p.local == "Cidade Teste/SP"
    assert len(p.horas) == 3
    assert p.horas[0] == datetime(2026, 8, 25, 0, 0)
    assert p.rajada_km_h == [12.0, 12.0, 12.0]
    assert p.do_cache is False


def test_respeita_o_limite_de_horas(monkeypatch):
    fingir_api(monkeypatch, resposta(horas=48))
    assert len(open_meteo.buscar_previsao(CIDADE, horas=24).horas) == 24


def test_serie_mais_curta_e_completada_com_none(monkeypatch):
    # a API pode devolver menos pontos numa variável do que em outra
    bruto = resposta(horas=3)
    bruto["hourly"]["cape"] = [100.0]
    fingir_api(monkeypatch, bruto)
    p = open_meteo.buscar_previsao(CIDADE, horas=3)
    assert p.cape_j_kg == [100.0, None, None]


def test_nulo_da_api_nao_virou_zero(monkeypatch):
    """Zero é medição válida; confundir com ausência falsearia a classificação."""
    bruto = resposta(horas=2)
    bruto["hourly"]["precipitation"] = [None, 0.0]
    fingir_api(monkeypatch, bruto)
    p = open_meteo.buscar_previsao(CIDADE, horas=2)
    assert p.precipitacao_mm == [None, 0.0]


def test_resposta_sem_serie_horaria_falha_claro(monkeypatch):
    fingir_api(monkeypatch, {"latitude": -23.5})
    with pytest.raises(open_meteo.ErroColeta, match="sem serie horaria"):
        open_meteo.buscar_previsao(CIDADE)


# ---------------------------------------------------------------------------
# A.2 — cache
# ---------------------------------------------------------------------------


def test_segunda_chamada_nao_toca_a_rede(monkeypatch):
    chamadas: list[str] = []
    fingir_api(monkeypatch, resposta(), contador=chamadas)

    primeira = open_meteo.buscar_previsao(CIDADE, horas=3)
    segunda = open_meteo.buscar_previsao(CIDADE, horas=3)

    assert len(chamadas) == 1
    assert primeira.do_cache is False
    assert segunda.do_cache is True


def test_cache_desligado_sempre_consulta(monkeypatch):
    chamadas: list[str] = []
    fingir_api(monkeypatch, resposta(), contador=chamadas)
    open_meteo.buscar_previsao(CIDADE, usar_cache=False)
    open_meteo.buscar_previsao(CIDADE, usar_cache=False)
    assert len(chamadas) == 2


# ---------------------------------------------------------------------------
# A.2 — falhas
# ---------------------------------------------------------------------------


def test_tenta_tres_vezes_antes_de_desistir(monkeypatch):
    chamadas: list[str] = []
    fingir_api(monkeypatch, erro=urllib.error.URLError("rede fora"), contador=chamadas)
    with pytest.raises(open_meteo.ErroColeta):
        open_meteo.buscar_previsao(CIDADE)
    assert len(chamadas) == open_meteo.TENTATIVAS


def test_cache_vencido_salva_a_demonstracao(monkeypatch, cache_isolado):
    # primeira chamada com rede boa: grava o cache
    fingir_api(monkeypatch, resposta(horas=3))
    open_meteo.buscar_previsao(CIDADE, horas=3)

    # o cache vence
    for arq in cache_isolado.glob("*.json"):
        import os
        os.utime(arq, (0, 0))

    # rede cai: o dado antigo é usado em vez de estourar erro
    fingir_api(monkeypatch, erro=urllib.error.URLError("rede fora"))
    p = open_meteo.buscar_previsao(CIDADE, horas=3)
    assert p.do_cache is True
    assert len(p.horas) == 3


def test_sem_cache_nenhum_a_falha_sobe(monkeypatch):
    fingir_api(monkeypatch, erro=urllib.error.URLError("rede fora"))
    with pytest.raises(open_meteo.ErroColeta, match="nao foi possivel consultar"):
        open_meteo.buscar_previsao(CIDADE)


def test_json_corrompido_conta_como_falha(monkeypatch):
    fingir_api(monkeypatch, erro=json.JSONDecodeError("ruim", "", 0))
    with pytest.raises(open_meteo.ErroColeta):
        open_meteo.buscar_previsao(CIDADE)


# ---------------------------------------------------------------------------
# Várias cidades
# ---------------------------------------------------------------------------


def test_uma_cidade_com_falha_nao_derruba_as_outras(monkeypatch):
    boa = Cidade(nome="Boa", uf="SP", latitude=-23.0, longitude=-46.0)
    ruim = Cidade(nome="Ruim", uf="RJ", latitude=-22.0, longitude=-43.0)

    def falso(url):
        if "latitude=-22.0" in url:
            raise urllib.error.URLError("essa falha")
        return resposta()

    monkeypatch.setattr(open_meteo, "_baixar", falso)
    previsoes, falhas = open_meteo.buscar_varias([boa, ruim], horas=3)

    assert [p.cidade for p in previsoes] == ["Boa"]
    assert [c.nome for c, _ in falhas] == ["Ruim"]
