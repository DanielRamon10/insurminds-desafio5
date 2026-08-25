"""Cliente da Open-Meteo — tarefas A.1 e A.2.

A Open-Meteo não exige chave nem cadastro para uso não comercial, o que remove
uma credencial do projeto. As cinco variáveis consumidas estão em
`config.VARIAVEIS_HORARIAS`, cada uma sustentando ao menos um evento.

Tolerância a falha (A.2), em três camadas:

1. **Cache em disco** por cidade e hora. A previsão não muda de minuto a minuto,
   então a segunda chamada da mesma hora não toca a rede — o que importa numa
   demonstração com 15 cidades.
2. **Novas tentativas com espera crescente** em falha de rede.
3. **Cache vencido como último recurso.** Se a rede falhar em todas as
   tentativas e houver cache expirado, ele é usado com aviso. Dado de uma hora
   atrás é muito melhor que erro na hora da apresentação.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from ..config import (
    CACHE_DIR,
    FUSO,
    JANELA_HORAS,
    OPEN_METEO_URL,
    VARIAVEIS_HORARIAS,
)
from ..schemas import Cidade, PrevisaoHoraria

log = logging.getLogger(__name__)

TENTATIVAS = 3
ESPERA_INICIAL = 2.0
TIMEOUT = 30
VALIDADE_CACHE_S = 3600  # a previsão é revista de hora em hora na origem


class ErroColeta(Exception):
    """Falha ao obter a previsão, com todas as saídas já esgotadas."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _caminho_cache(cidade: Cidade, horas: int) -> Path:
    marca = datetime.now().strftime("%Y%m%d%H")
    nome = f"{cidade.nome}_{cidade.uf}_{horas}h_{marca}".lower().replace(" ", "-")
    return CACHE_DIR / f"{nome}.json"


def _ler_cache(caminho: Path, aceitar_vencido: bool = False) -> dict | None:
    if not caminho.is_file():
        return None
    idade = time.time() - caminho.stat().st_mtime
    if idade > VALIDADE_CACHE_S and not aceitar_vencido:
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gravar_cache(caminho: Path, dados: dict) -> None:
    try:
        caminho.write_text(json.dumps(dados), encoding="utf-8")
    except OSError as exc:  # cache é conveniência: falhar aqui não é fatal
        log.warning("nao foi possivel gravar o cache %s: %s", caminho.name, exc)


def _cache_vencido_mais_recente(cidade: Cidade, horas: int) -> Path | None:
    """Qualquer cache anterior desta cidade, para o último recurso."""
    padrao = f"{cidade.nome}_{cidade.uf}_{horas}h_*".lower().replace(" ", "-")
    candidatos = sorted(CACHE_DIR.glob(f"{padrao}.json"), key=lambda p: p.stat().st_mtime)
    return candidatos[-1] if candidatos else None


# ---------------------------------------------------------------------------
# Chamada à API
# ---------------------------------------------------------------------------


def _montar_url(cidade: Cidade, horas: int) -> str:
    parametros = {
        "latitude": cidade.latitude,
        "longitude": cidade.longitude,
        "hourly": ",".join(VARIAVEIS_HORARIAS),
        "timezone": FUSO,
        "forecast_days": max(1, min(3, (horas + 23) // 24)),
    }
    return f"{OPEN_METEO_URL}?{urllib.parse.urlencode(parametros)}"


def _baixar(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resposta:
        return json.load(resposta)


def _buscar_com_tentativas(cidade: Cidade, horas: int) -> dict:
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return _baixar(_montar_url(cidade, horas))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            ultimo_erro = exc
            if tentativa < TENTATIVAS:
                espera = ESPERA_INICIAL * (2 ** (tentativa - 1))
                log.warning(
                    "falha ao consultar %s (tentativa %d/%d): %s — aguardando %.0fs",
                    cidade, tentativa, TENTATIVAS, exc, espera,
                )
                time.sleep(espera)
    raise ErroColeta(f"nao foi possivel consultar a previsao de {cidade}") from ultimo_erro


# ---------------------------------------------------------------------------
# Conversão para o contrato
# ---------------------------------------------------------------------------


def _converter(cidade: Cidade, bruto: dict, horas: int, do_cache: bool) -> PrevisaoHoraria:
    horario = bruto.get("hourly")
    if not horario or "time" not in horario:
        raise ErroColeta(f"resposta sem serie horaria para {cidade}")

    def serie(nome: str) -> list:
        return horario.get(nome, [])[:horas]

    momentos = [datetime.fromisoformat(t) for t in serie("time")]
    if not momentos:
        raise ErroColeta(f"serie horaria vazia para {cidade}")

    n = len(momentos)

    def numeros(nome: str) -> list[float | None]:
        valores = serie(nome)
        # a API pode devolver a série mais curta que o pedido; completa com None
        return [None if v is None else float(v) for v in valores] + [None] * (n - len(valores))

    def inteiros(nome: str) -> list[int | None]:
        valores = serie(nome)
        return [None if v is None else int(v) for v in valores] + [None] * (n - len(valores))

    return PrevisaoHoraria(
        cidade=cidade.nome,
        uf=cidade.uf,
        horas=momentos,
        precipitacao_mm=numeros("precipitation"),
        rajada_km_h=numeros("wind_gusts_10m"),
        codigo_wmo=inteiros("weather_code"),
        cape_j_kg=numeros("cape"),
        nivel_congelamento_m=numeros("freezing_level_height"),
        do_cache=do_cache,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def buscar_previsao(
    cidade: Cidade,
    horas: int = JANELA_HORAS,
    usar_cache: bool = True,
) -> PrevisaoHoraria:
    """Obtém a previsão horária de uma cidade.

    Levanta `ErroColeta` apenas quando a rede falha e não há nenhum cache —
    nem vencido — para servir de alternativa.
    """
    caminho = _caminho_cache(cidade, horas)

    if usar_cache and (guardado := _ler_cache(caminho)) is not None:
        log.debug("previsao de %s vinda do cache", cidade)
        return _converter(cidade, guardado, horas, do_cache=True)

    try:
        bruto = _buscar_com_tentativas(cidade, horas)
    except ErroColeta:
        antigo = _cache_vencido_mais_recente(cidade, horas)
        vencido = _ler_cache(antigo, aceitar_vencido=True) if antigo else None
        if vencido is None:
            raise
        log.warning(
            "rede indisponivel para %s: usando cache vencido de %s",
            cidade,
            datetime.fromtimestamp(antigo.stat().st_mtime).strftime("%d/%m %H:%M"),
        )
        return _converter(cidade, vencido, horas, do_cache=True)

    if usar_cache:
        _gravar_cache(caminho, bruto)
    return _converter(cidade, bruto, horas, do_cache=False)


def buscar_varias(
    cidades: list[Cidade],
    horas: int = JANELA_HORAS,
    usar_cache: bool = True,
) -> tuple[list[PrevisaoHoraria], list[tuple[Cidade, str]]]:
    """Consulta várias cidades sem deixar uma falha derrubar as demais.

    Devolve as previsões obtidas e a lista de cidades que falharam com o motivo.
    """
    previsoes: list[PrevisaoHoraria] = []
    falhas: list[tuple[Cidade, str]] = []
    for cidade in cidades:
        try:
            previsoes.append(buscar_previsao(cidade, horas, usar_cache))
        except ErroColeta as exc:
            falhas.append((cidade, str(exc)))
            log.error("%s ficou de fora: %s", cidade, exc)
    return previsoes, falhas
