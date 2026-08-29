"""Modo cenário forçado — tarefa D.2.

Injeta condições climáticas extremas sem depender do tempo real. Sem isto, um
dia de céu limpo na apresentação significa nenhum evento e nenhuma mensagem
para mostrar — o roteiro chama isto de "disparar qualquer cenário sob encomenda".

Os valores fabricados respeitam dois compromissos:

* **Atravessam o mesmo caminho que o dado real.** O que sai daqui é uma
  `PrevisaoHoraria` como a Open-Meteo produziria; o classificador da frente B,
  as regras de negócio e a redação não sabem que a origem foi um cenário.
* **Ultrapassam os limiares de `data/regras.yaml` com folga**, na severidade
  pedida — então o resultado da classificação é determinístico e a demo nunca
  surpreende. Os números foram calibrados contra os limiares da versão atual do
  especialista (regras.yaml v1); se os limiares mudarem, os testes avisam.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..config import JANELA_HORAS
from ..schemas import (
    Cidade,
    PrevisaoHoraria,
    Severidade,
    TipoEvento,
)

#: Fonte declarada pelos cenários — aparece nas mensagens e na caixa de saída.
FONTE_CENARIO = "cenario-forcado"

# ---------------------------------------------------------------------------
# Perfis numéricos por (evento, severidade)
#
# Cada perfil diz o valor usado nas posições relevantes da série horária.
# O resto da janela fica calmo, imitando uma previsão normal.
# ---------------------------------------------------------------------------

PERFIS: dict[tuple[TipoEvento, Severidade], dict[str, float | int]] = {
    # Chuva intensa: atenção 15–29 mm/h ou 40–59 mm acumulados; alerta acima disso
    (TipoEvento.CHUVA_INTENSA, Severidade.ATENCAO): {
        "precipitacao_mm_pico": 18.0, "precipitacao_mm_base": 1.0,
    },
    (TipoEvento.CHUVA_INTENSA, Severidade.ALERTA): {
        "precipitacao_mm_pico": 35.0, "precipitacao_mm_base": 2.0,
    },
    # Vento forte: atenção a partir de 60 km/h; alerta a partir de 80 km/h
    (TipoEvento.VENTO_FORTE, Severidade.ATENCAO): {"rajada_km_h": 65.0},
    (TipoEvento.VENTO_FORTE, Severidade.ALERTA): {"rajada_km_h": 92.0},
    # Raio: exige código WMO de trovoada E CAPE (combinacao: todos)
    (TipoEvento.RAIO, Severidade.ATENCAO): {"codigo_wmo": 95, "cape_j_kg": 900.0},
    (TipoEvento.RAIO, Severidade.ALERTA): {"codigo_wmo": 95, "cape_j_kg": 2200.0},
    # Granizo: CAPE alta E nível de congelamento baixo (quanto menor, pior)
    (TipoEvento.GRANIZO, Severidade.ATENCAO): {
        "cape_j_kg": 1700.0, "nivel_congelamento_m": 3400.0,
    },
    (TipoEvento.GRANIZO, Severidade.ALERTA): {
        "cape_j_kg": 2800.0, "nivel_congelamento_m": 2600.0,
    },
}

#: Nomes amigáveis para CLI e interface. A versão curta usa severidade ALERTA
#: (é a que rende a demo mais expressiva); cada evento tem a variante _atencao.
CENARIOS_FORCADOS: dict[str, tuple[TipoEvento, Severidade]] = {}
for _tipo in TipoEvento:
    for _sev in Severidade:
        _sufixo = "" if _sev is Severidade.ALERTA else "_atencao"
        CENARIOS_FORCADOS[f"{_tipo.value}{_sufixo}"] = (_tipo, _sev)


def listar_cenarios() -> list[str]:
    """Nomes válidos para `--cenario` no CLI e para o seletor na interface."""
    return sorted(CENARIOS_FORCADOS)


def previsao_cenario(
    nome: str,
    cidade: Cidade,
    horas: int = JANELA_HORAS,
    inicio: datetime | None = None,
) -> PrevisaoHoraria:
    """Constrói a série horária extrema de um cenário para uma cidade."""
    chave = nome.strip().lower()
    if chave not in CENARIOS_FORCADOS:
        raise KeyError(
            f"cenario desconhecido: '{nome}' (validos: {', '.join(listar_cenarios())})"
        )
    tipo, severidade = CENARIOS_FORCADOS[chave]
    perfil = PERFIS[(tipo, severidade)]

    comeco = inicio or datetime.now().replace(minute=0, second=0, microsecond=0)
    serie_horas = [comeco + timedelta(hours=i) for i in range(horas)]

    # Por padrão tudo calmo; as medidas do perfil são aplicadas à janela inteira,
    # com picos definidos abaixo quando o critério avalia hora isolada.
    precipitacao = [None] * horas
    rajada = [None] * horas
    codigo_wmo: list[int | None] = [None] * horas
    cape = [None] * horas
    nivel_congelamento = [None] * horas

    if "precipitacao_mm_pico" in perfil:
        base = float(perfil["precipitacao_mm_base"])
        pico = float(perfil["precipitacao_mm_pico"])
        precipitacao = [base] * horas
        precipitacao[horas // 3] = pico           # pico único no terço inicial
    if "rajada_km_h" in perfil:
        rajada = [float(perfil["rajada_km_h"])] * horas
    if "codigo_wmo" in perfil:
        codigo_wmo = [int(perfil["codigo_wmo"])] * horas
    if "cape_j_kg" in perfil:
        cape = [float(perfil["cape_j_kg"])] * horas
    if "nivel_congelamento_m" in perfil:
        nivel_congelamento = [float(perfil["nivel_congelamento_m"])] * horas

    return PrevisaoHoraria(
        cidade=cidade.nome,
        uf=cidade.uf,
        horas=serie_horas,
        precipitacao_mm=precipitacao,
        rajada_km_h=rajada,
        codigo_wmo=codigo_wmo,
        cape_j_kg=cape,
        nivel_congelamento_m=nivel_congelamento,
        fonte=FONTE_CENARIO,
    )
