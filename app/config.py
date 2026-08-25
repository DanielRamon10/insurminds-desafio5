"""Configuração central — tarefa F0.4.

Chaves de API **nunca** ficam no código: são lidas de variáveis de ambiente
(arquivo `.env` local) ou de `st.secrets` quando a aplicação roda no Streamlit
Cloud. O `.env` está no `.gitignore`.

A fonte de dados meteorológicos (Open-Meteo) não exige chave. A credencial é
necessária apenas para o modelo de linguagem que redige as mensagens.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .schemas import Cidade

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / ".cache"

CACHE_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Fonte de dados meteorológicos
# ---------------------------------------------------------------------------

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

#: Variáveis horárias consumidas da API. Cada uma sustenta ao menos um evento:
#: precipitação -> chuva intensa · rajada -> vento forte
#: código WMO + CAPE -> raio · CAPE + nível de congelamento -> granizo
VARIAVEIS_HORARIAS = (
    "precipitation",
    "wind_gusts_10m",
    "weather_code",
    "cape",
    "freezing_level_height",
)

FUSO = "America/Sao_Paulo"

#: Janela de agregação do evento, em horas (ver decisão 1 em schemas.py).
JANELA_HORAS = 24

#: Códigos WMO de trovoada. 96 e 99 (com granizo) não são preenchidos no
#: Brasil — só na Europa Central — por isso granizo usa o nível de congelamento.
CODIGOS_TROVOADA = frozenset({95, 96, 99})


# ---------------------------------------------------------------------------
# Provedores de LLM
# ---------------------------------------------------------------------------

PROVEDORES: dict[str, dict[str, object]] = {
    "google": {
        "rotulo": "Google (Gemini)",
        "env_key": "GOOGLE_API_KEY",
        "modelo_padrao": "gemini-3.6-flash",
        # Todos na camada gratuita. Cada modelo tem cota diária própria: se um
        # esgotar, trocar para o seguinte da lista resolve sem esperar o dia virar.
        "modelos": [
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ],
        "pacote": "langchain-google-genai",
    },
    "anthropic": {
        "rotulo": "Anthropic (Claude)",
        "env_key": "ANTHROPIC_API_KEY",
        "modelo_padrao": "claude-sonnet-5",
        "modelos": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"],
        "pacote": "langchain-anthropic",
    },
    "openai": {
        "rotulo": "OpenAI (GPT)",
        "env_key": "OPENAI_API_KEY",
        "modelo_padrao": "gpt-4.1",
        "modelos": ["gpt-4.1", "gpt-4.1-mini"],
        "pacote": "langchain-openai",
    },
}


@dataclass
class ConfigLLM:
    """Provedor e modelo em uso, resolvidos a partir do ambiente."""

    provedor: str = os.getenv("LLM_PROVIDER", "google")
    modelo: str = os.getenv("LLM_MODEL", "")
    max_tentativas: int = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))

    def __post_init__(self) -> None:
        if self.provedor not in PROVEDORES:
            raise ValueError(
                f"Provedor '{self.provedor}' invalido. "
                f"Use um de: {', '.join(PROVEDORES)}"
            )
        if not self.modelo:
            self.modelo = str(PROVEDORES[self.provedor]["modelo_padrao"])

    @property
    def env_key(self) -> str:
        return str(PROVEDORES[self.provedor]["env_key"])


def obter_api_key(provedor: str) -> str | None:
    """Busca a chave no ambiente e, se disponível, em `st.secrets`."""
    env_key = str(PROVEDORES[provedor]["env_key"])
    if valor := os.getenv(env_key):
        return valor
    try:  # Streamlit Cloud
        import streamlit as st

        return st.secrets.get(env_key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cidades monitoradas
# ---------------------------------------------------------------------------


def carregar_cidades(caminho: Path | None = None) -> list[Cidade]:
    """Lê as cidades monitoradas de `data/cidades.csv`.

    As coordenadas são reais e foram verificadas contra a API. As regiões
    cobrem perfis climáticos distintos, para que os quatro eventos tenham
    chance de aparecer. O código IBGE vem da API de localidades do próprio
    IBGE e serve para casar os avisos oficiais do INMET.
    """
    caminho = caminho or DATA_DIR / "cidades.csv"
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de cidades nao encontrado: {caminho}")

    with caminho.open(encoding="utf-8", newline="") as f:
        return [
            Cidade(
                nome=linha["nome"],
                uf=linha["uf"],
                latitude=float(linha["latitude"]),
                longitude=float(linha["longitude"]),
                codigo_ibge=(linha.get("codigo_ibge") or "").strip() or None,
            )
            for linha in csv.DictReader(f)
        ]
