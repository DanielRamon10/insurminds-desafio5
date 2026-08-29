"""Carregador da base sintética de segurados — apoio à Frente D.

A base mora em `data/segurados.csv` (tarefa B.1) e este módulo apenas a traz
para o contrato `Segurado`. Vive aqui e não dentro do motor de regras porque a
decisão de *quem* avisar é da frente B; o pipeline de demonstração só precisa da
lista pronta. As linhas malformadas falham com mensagem clara, em vez de virar
segurado pela metade silenciosamente.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from ..config import DATA_DIR
from ..schemas import Canal, Segurado, TipoApolice


def carregar_segurados(caminho: Path | None = None) -> list[Segurado]:
    """Lê `data/segurados.csv` e devolve a base já tipada pelo contrato."""
    caminho = caminho or DATA_DIR / "segurados.csv"
    if not caminho.is_file():
        raise FileNotFoundError(f"Base de segurados nao encontrada: {caminho}")

    segurados: list[Segurado] = []
    with caminho.open(encoding="utf-8", newline="") as f:
        for numero, linha in enumerate(csv.DictReader(f), start=2):
            try:
                segurados.append(
                    Segurado(
                        id=linha["id"].strip(),
                        nome=linha["nome"].strip(),
                        tipo_apolice=TipoApolice(linha["tipo_apolice"].strip()),
                        cidade=linha["cidade"].strip(),
                        uf=linha["uf"].strip(),
                        latitude=float(linha["latitude"]),
                        longitude=float(linha["longitude"]),
                        canal=Canal(linha["canal"].strip()),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(
                    f"{caminho.name}, linha {numero}: registro invalido "
                    f"({exc.__class__.__name__}: {exc})"
                ) from exc
    return segurados


if __name__ == "__main__":  # conferência rápida: python -m app.domain.segurados
    base = carregar_segurados()
    por_apolice: dict[str, int] = {}
    for s in base:
        por_apolice[s.tipo_apolice.value] = por_apolice.get(s.tipo_apolice.value, 0) + 1
    print(f"{len(base)} segurados carregados de data/segurados.csv")
    for apolice, quantidade in sorted(por_apolice.items()):
        print(f"  {apolice}: {quantidade}")
    sys.exit(0)
