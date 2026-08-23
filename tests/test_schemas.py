"""Testes dos contratos de dados — e exemplo de uso para as frentes A, B, C e D.

Rode com:
    python -m pytest tests/ -v
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import JANELA_HORAS, carregar_cidades
from app.schemas import (
    CENARIOS_ATIVOS,
    LIMITE_CARACTERES,
    Canal,
    EventoClimatico,
    Medidas,
    Notificacao,
    Segurado,
    Severidade,
    StatusEnvio,
    TipoApolice,
    TipoEvento,
)

AGORA = datetime(2026, 8, 22, 18, 0)


def _evento(tipo: TipoEvento, **medidas) -> EventoClimatico:
    return EventoClimatico(
        cidade="Porto Alegre",
        uf="rs",
        tipo=tipo,
        severidade=Severidade.ALERTA,
        inicio=AGORA,
        fim=AGORA + timedelta(hours=JANELA_HORAS),
        medidas=Medidas(**medidas),
    )


# ---------------------------------------------------------------------------
# Cidades
# ---------------------------------------------------------------------------


def test_cidades_carregam_e_cobrem_o_pais():
    cidades = carregar_cidades()
    assert len(cidades) == 15
    ufs = {c.uf for c in cidades}
    # Sul (granizo), litoral (vento) e Norte (raio) precisam estar representados
    assert {"RS", "SC", "PR"} & ufs, "faltam cidades do Sul"
    assert {"AM", "PA"} & ufs, "faltam cidades do Norte"


def test_coordenadas_dentro_do_brasil():
    for c in carregar_cidades():
        assert -34 <= c.latitude <= 6, f"latitude fora do Brasil: {c}"
        assert -74 <= c.longitude <= -34, f"longitude fora do Brasil: {c}"


# ---------------------------------------------------------------------------
# Segurado
# ---------------------------------------------------------------------------


def test_uf_normalizada_para_maiuscula():
    s = Segurado(
        id="SEG-001",
        nome="Maria Souza",
        tipo_apolice=TipoApolice.RESIDENCIAL,
        cidade="Curitiba",
        uf="pr",
        latitude=-25.43,
        longitude=-49.27,
        canal=Canal.SMS,
    )
    assert s.uf == "PR"
    assert s.local == "Curitiba/PR"


def test_apolice_invalida_e_recusada():
    with pytest.raises(ValidationError):
        Segurado(
            id="SEG-002",
            nome="Joao Lima",
            tipo_apolice="empresarial",  # fora do vocabulário decidido
            cidade="Recife",
            uf="PE",
            latitude=-8.05,
            longitude=-34.88,
            canal=Canal.EMAIL,
        )


# ---------------------------------------------------------------------------
# EventoClimatico
# ---------------------------------------------------------------------------


def test_janela_invertida_e_recusada():
    with pytest.raises(ValidationError):
        EventoClimatico(
            cidade="Santos",
            uf="SP",
            tipo=TipoEvento.VENTO_FORTE,
            severidade=Severidade.ATENCAO,
            inicio=AGORA,
            fim=AGORA - timedelta(hours=1),
            medidas=Medidas(rajada_km_h=70),
        )


def test_medidas_expoem_apenas_o_que_foi_medido():
    ev = _evento(TipoEvento.GRANIZO, cape_j_kg=1900, nivel_congelamento_m=3100, codigo_wmo=95)
    assert ev.medidas.preenchidas() == {
        "cape_j_kg": 1900,
        "nivel_congelamento_m": 3100,
        "codigo_wmo": 95,
    }
    assert ev.medidas.precipitacao_mm_h is None


def test_matriz_de_cenarios_tem_sete_combinacoes():
    assert len(CENARIOS_ATIVOS) == 7


def test_raio_nao_atinge_apolice_automotiva():
    # um automóvel é uma gaiola de Faraday: sem recomendação honesta a dar
    raio = _evento(TipoEvento.RAIO, codigo_wmo=95, cape_j_kg=1200)
    assert raio.atinge(TipoApolice.RESIDENCIAL)
    assert not raio.atinge(TipoApolice.AUTOMOTIVA)


def test_granizo_atinge_as_duas_apolices():
    granizo = _evento(TipoEvento.GRANIZO, cape_j_kg=2100, nivel_congelamento_m=2900)
    assert granizo.atinge(TipoApolice.RESIDENCIAL)
    assert granizo.atinge(TipoApolice.AUTOMOTIVA)


# ---------------------------------------------------------------------------
# Notificacao
# ---------------------------------------------------------------------------


def _notificacao(mensagem: str, canal: Canal = Canal.SMS) -> Notificacao:
    return Notificacao(
        segurado_id="SEG-001",
        segurado_nome="Maria Souza",
        tipo_apolice=TipoApolice.RESIDENCIAL,
        evento=_evento(TipoEvento.CHUVA_INTENSA, precipitacao_mm_janela=52.0),
        canal=canal,
        mensagem=mensagem,
        regra_acionada="chuva_intensa/residencial/alerta",
        gerada_em=AGORA,
    )


def test_notificacao_nasce_pendente():
    n = _notificacao("Previsao de 52 mm de chuva nas proximas 24h em Porto Alegre.")
    assert n.status is StatusEnvio.PENDENTE
    assert n.dentro_do_limite()


def test_mensagem_vazia_e_recusada():
    with pytest.raises(ValidationError):
        _notificacao("   ")


def test_limite_de_sms_e_verificavel():
    longa = "A" * (LIMITE_CARACTERES[Canal.SMS] + 1)
    assert not _notificacao(longa, Canal.SMS).dentro_do_limite()
    # a mesma mensagem cabe por e-mail
    assert _notificacao(longa, Canal.EMAIL).dentro_do_limite()
