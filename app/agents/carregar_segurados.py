"""Carrega data/segurados.csv (tarefa B.1) para objetos Segurado.

Simétrico ao carregar_cidades() que já existe em app/config.py — não
mexi nesse arquivo, só segui o mesmo padrão aqui, porque o loader de
segurados ainda não tinha dono.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..config import DATA_DIR
from ..schemas import Segurado


def carregar_segurados(caminho: Path | None = None) -> list[Segurado]:
    caminho = caminho or DATA_DIR / "segurados.csv"
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de segurados nao encontrado: {caminho}")

    with caminho.open(encoding="utf-8", newline="") as f:
        return [Segurado(**linha) for linha in csv.DictReader(f)]
