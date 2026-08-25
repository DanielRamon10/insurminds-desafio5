"""Cliente de alertas oficiais do INMET — tarefa A.4.

Segunda fonte de dados, complementar à Open-Meteo e de natureza diferente:
enquanto a previsão numérica dá os números que o classificador interpreta, aqui
o Instituto Nacional de Meteorologia já decidiu que há risco e publicou o aviso.

O papel é de **enriquecimento**, não de validação. A classificação continua
saindo dos limiares definidos pelo especialista; o aviso oficial, quando existe,
acrescenta contexto e instruções redigidas por órgão público.

Limitação medida em 25/08/2026, e a razão de não tratar isto como validação
cruzada: um único aviso de "Tempestade" cobria **1.987 municípios**. Um alerta
dessa extensão é uma afirmação sobre a *região*, não sobre a coordenada da
capital — naquele dia o INMET alertava para 9 das nossas cidades enquanto a
previsão numérica no ponto exato de cada uma mostrava menos de 2 mm de chuva.

As duas fontes não se contradizem: elas respondem perguntas diferentes. A
previsão diz o que se espera naquele ponto; o aviso diz que a região está sob
vigilância. Por isso a ausência de aviso oficial nunca derruba um evento
classificado, e a presença dele nunca cria um.

A API é aberta e não exige chave. Um único endpoint devolve todos os avisos
ativos do país, então basta uma chamada por execução — não uma por cidade.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from ..config import CACHE_DIR
from ..schemas import AlertaOficial, Cidade

log = logging.getLogger(__name__)

INMET_AVISOS_URL = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
TENTATIVAS = 2
ESPERA_INICIAL = 2.0
TIMEOUT = 30
VALIDADE_CACHE_S = 1800  # avisos mudam mais rápido que a previsão

#: A API não expõe os avisos como JSON puro em todos os campos: `riscos` e
#: `instrucoes` chegam como a repr de uma lista Python entre aspas simples.
_RE_ITEM = re.compile(r"'((?:[^'\\]|\\.)*)'")


class ErroAlertas(Exception):
    """Falha ao obter os avisos oficiais."""


# ---------------------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------------------


def _lista_de_texto(valor: object) -> list[str]:
    """Converte o campo de lista da API numa lista de verdade.

    Aceita lista real, string com repr de lista, ou texto simples.
    """
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    if not isinstance(valor, str) or not valor.strip():
        return []
    achados = [m.group(1).strip() for m in _RE_ITEM.finditer(valor)]
    if achados:
        return [a.replace("\\'", "'") for a in achados if a]
    return [valor.strip()]


def _codigos(valor: object) -> set[str]:
    """Extrai os códigos IBGE do campo `geocodes`."""
    if isinstance(valor, list):
        return {str(v).strip() for v in valor if str(v).strip()}
    if isinstance(valor, str):
        return {p.strip() for p in valor.split(",") if p.strip()}
    return set()


def _momento(data: object, hora: object) -> datetime | None:
    """Combina os campos de data e hora do aviso.

    A API traz `inicio`/`fim` já formatados e também `data_inicio` em UTC com
    `hora_inicio` separada. O par formatado é o mais confiável.
    """
    if isinstance(data, str) and data.strip():
        texto = data.strip()
        for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(texto[:19], formato)
            except ValueError:
                continue
    return None


def _converter(bruto: dict) -> AlertaOficial | None:
    inicio = _momento(bruto.get("inicio"), bruto.get("hora_inicio"))
    fim = _momento(bruto.get("fim"), bruto.get("hora_fim"))
    if inicio is None or fim is None or fim <= inicio:
        # sem janela utilizável o aviso não serve para cruzar com a previsão
        return None

    return AlertaOficial(
        id=str(bruto.get("id_aviso") or bruto.get("id") or "sem-id"),
        titulo=str(bruto.get("descricao") or "Aviso meteorológico").strip(),
        severidade=str(bruto.get("severidade") or "").strip(),
        inicio=inicio,
        fim=fim,
        riscos=_lista_de_texto(bruto.get("riscos")),
        instrucoes=_lista_de_texto(bruto.get("instrucoes")),
        codigos_ibge=_codigos(bruto.get("geocodes")),
    )


# ---------------------------------------------------------------------------
# Rede e cache
# ---------------------------------------------------------------------------


def _caminho_cache() -> Path:
    marca = datetime.now().strftime("%Y%m%d%H%M")[:-1]  # granularidade de 10 min
    return CACHE_DIR / f"inmet-avisos-{marca}0.json"


def _baixar(url: str) -> dict:
    pedido = urllib.request.Request(url, headers={"User-Agent": "insurminds-desafio5"})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT) as resposta:
        corpo = resposta.read()
    if corpo[:2] == b"\x1f\x8b":  # a API pode responder comprimido
        corpo = gzip.decompress(corpo)
    return json.loads(corpo.decode("utf-8"))


def _buscar_bruto() -> dict:
    caminho = _caminho_cache()
    if caminho.is_file() and time.time() - caminho.stat().st_mtime <= VALIDADE_CACHE_S:
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    ultimo: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            dados = _baixar(INMET_AVISOS_URL)
            try:
                caminho.write_text(json.dumps(dados), encoding="utf-8")
            except OSError:
                pass
            return dados
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            ultimo = exc
            if tentativa < TENTATIVAS:
                time.sleep(ESPERA_INICIAL * tentativa)
    raise ErroAlertas("nao foi possivel consultar os avisos do INMET") from ultimo


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def buscar_alertas() -> list[AlertaOficial]:
    """Todos os avisos oficiais ativos, de hoje e dos próximos dias.

    Uma chamada cobre o país inteiro. Diferente da coleta de previsão, a falha
    aqui **não é fatal**: a solução funciona sem a segunda fonte, então quem
    chama pode simplesmente seguir com a lista vazia.
    """
    bruto = _buscar_bruto()
    grupos = (
        [bruto.get("hoje") or [], bruto.get("futuro") or []]
        if isinstance(bruto, dict)
        else [bruto or []]
    )

    alertas: list[AlertaOficial] = []
    for grupo in grupos:
        for item in grupo:
            if not isinstance(item, dict) or item.get("encerrado"):
                continue
            if (alerta := _converter(item)) is not None:
                alertas.append(alerta)

    log.info("INMET: %d avisos ativos", len(alertas))
    return alertas


def buscar_alertas_tolerante() -> list[AlertaOficial]:
    """Como `buscar_alertas`, mas devolve lista vazia em caso de falha.

    A segunda fonte é um reforço: sua indisponibilidade não deve interromper o
    fluxo nem aparecer como erro para o usuário.
    """
    try:
        return buscar_alertas()
    except ErroAlertas as exc:
        log.warning("seguindo sem os avisos do INMET: %s", exc)
        return []


def alertas_da_cidade(
    alertas: list[AlertaOficial],
    cidade: Cidade,
    inicio: datetime | None = None,
    fim: datetime | None = None,
) -> list[AlertaOficial]:
    """Filtra os avisos que cobrem a cidade e a janela informada.

    O casamento é por **código IBGE**, nunca por nome: o campo de municípios da
    API lista centenas de nomes, e uma busca textual faria "Santos" casar com
    "Santos Dumont".
    """
    if not cidade.codigo_ibge:
        return []

    def na_janela(a: AlertaOficial) -> bool:
        if inicio is None or fim is None:
            return True
        return a.inicio <= fim and a.fim >= inicio  # sobreposição

    return [a for a in alertas if a.cobre(cidade) and na_janela(a)]
