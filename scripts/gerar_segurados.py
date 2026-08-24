"""Gera a base sintética de segurados — apoio à tarefa B.1.

Os segurados são fictícios; as cidades e coordenadas são reais (`data/cidades.csv`),
porque a API meteorológica precisa de coordenada verdadeira.

A distribuição é determinística (semente fixa), então rodar de novo produz
exatamente a mesma base — importante para a demonstração ser reproduzível.

Uso:
    python scripts/gerar_segurados.py              # grava data/segurados.csv
    python scripts/gerar_segurados.py --conferir   # só valida a base existente
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.config import carregar_cidades  # noqa: E402
from app.schemas import (  # noqa: E402
    CENARIOS_ATIVOS,
    Canal,
    Segurado,
    TipoApolice,
)

SEMENTE = 42
POR_CIDADE = 3  # 15 cidades x 3 = 45 segurados

NOMES = [
    "Ana Beatriz Cardoso", "Bruno Tavares Lima", "Carla Menezes Rocha",
    "Diego Antunes Prado", "Eliane Barros Nunes", "Fabio Correia Mendes",
    "Gabriela Pinto Serra", "Henrique Vasques Alves", "Isabela Moraes Freitas",
    "Joao Pedro Bastos", "Karina Duarte Peixoto", "Leandro Figueira Sampaio",
    "Mariana Teixeira Couto", "Nelson Aguiar Fontes", "Olivia Ramos Bittencourt",
    "Paulo Cesar Andrade", "Queren Lopes Vidal", "Rafael Siqueira Braga",
    "Simone Carvalho Reis", "Tiago Monteiro Guedes", "Ursula Batista Amaral",
    "Vinicius Pacheco Leal", "Wanda Ferreira Goulart", "Xavier Nogueira Pires",
    "Yasmin Cordeiro Beltrao", "Zeca Almeida Rangel", "Alice Furtado Neves",
    "Bernardo Cunha Salles", "Camila Esteves Pontes", "Danilo Rezende Xavier",
    "Erika Salgado Vieira", "Felipe Drummond Castro", "Giovana Lacerda Prado",
    "Hugo Martins Quintela", "Ines Bandeira Marques", "Julio Cesar Trindade",
    "Larissa Fontoura Dias", "Marcos Vinicius Coelho", "Natalia Berto Assis",
    "Otavio Pimentel Faria", "Priscila Guimaraes Sa", "Renato Bulhoes Melo",
    "Sabrina Veloso Tavares", "Thiago Arruda Pontes", "Valeria Nascimento Rios",
]


def gerar() -> list[Segurado]:
    aleatorio = random.Random(SEMENTE)
    cidades = carregar_cidades()
    nomes = list(NOMES)
    aleatorio.shuffle(nomes)

    segurados: list[Segurado] = []
    for indice_cidade, cidade in enumerate(cidades):
        for posicao in range(POR_CIDADE):
            # alterna as apólices para nenhuma cidade ficar só com um tipo
            apolice = (
                TipoApolice.RESIDENCIAL
                if (indice_cidade + posicao) % 2 == 0
                else TipoApolice.AUTOMOTIVA
            )
            segurados.append(
                Segurado(
                    id=f"SEG-{len(segurados) + 1:03d}",
                    nome=nomes[len(segurados) % len(nomes)],
                    tipo_apolice=apolice,
                    cidade=cidade.nome,
                    uf=cidade.uf,
                    latitude=cidade.latitude,
                    longitude=cidade.longitude,
                    canal=aleatorio.choice(list(Canal)),
                )
            )
    return segurados


def conferir(segurados: list[Segurado]) -> list[str]:
    """Verifica o critério de pronto da B.1: todo cenário tem alguém elegível."""
    problemas: list[str] = []
    apolices_presentes = {s.tipo_apolice for s in segurados}

    for evento, apolice in sorted(CENARIOS_ATIVOS, key=lambda c: (c[0].value, c[1].value)):
        if apolice not in apolices_presentes:
            problemas.append(f"nenhum segurado com apolice {apolice.value} para {evento.value}")

    if len({s.cidade for s in segurados}) < 15:
        problemas.append("nem todas as 15 cidades tem segurado")
    if len({s.id for s in segurados}) != len(segurados):
        problemas.append("ha ids repetidos")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera a base sintetica de segurados.")
    parser.add_argument("--conferir", action="store_true", help="Apenas valida, nao grava.")
    args = parser.parse_args()

    destino = RAIZ / "data" / "segurados.csv"
    segurados = gerar()

    problemas = conferir(segurados)
    if problemas:
        print("Base inconsistente:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"{len(segurados)} segurados em {len({s.cidade for s in segurados})} cidades")
    for apolice in TipoApolice:
        n = sum(1 for s in segurados if s.tipo_apolice is apolice)
        print(f"  {apolice.value:<12} {n:>3}")
    for canal in Canal:
        n = sum(1 for s in segurados if s.canal is canal)
        print(f"  {canal.value:<12} {n:>3}")

    if args.conferir:
        print("\nConferencia OK — nada gravado.")
        return 0

    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(
            ["id", "nome", "tipo_apolice", "cidade", "uf", "latitude", "longitude", "canal"]
        )
        for s in segurados:
            escritor.writerow(
                [s.id, s.nome, s.tipo_apolice.value, s.cidade, s.uf,
                 s.latitude, s.longitude, s.canal.value]
            )
    print(f"\nGravado: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
