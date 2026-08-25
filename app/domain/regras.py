"""Leitura e validação do arquivo de regras — apoio às tarefas B.2 e B.3.

As regras vivem em `data/regras.yaml` justamente para poderem ser alteradas por
quem não programa. O preço disso é que o arquivo pode chegar inconsistente, então
tudo é validado na carga: nome de evento fora do vocabulário, medida que não
existe no contrato ou cenário duplicado falham aqui, com mensagem clara, em vez
de virar comportamento errado silencioso na classificação.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

from ..config import DATA_DIR
from ..schemas import Medidas, Severidade, TipoApolice, TipoEvento


class ErroRegras(Exception):
    """Arquivo de regras inconsistente."""


class Combinacao(str, Enum):
    """Como avaliar múltiplos critérios de um mesmo evento."""

    QUALQUER = "qualquer"  # basta um atingir o limiar
    TODOS = "todos"        # todos precisam atingir


class Comparacao(str, Enum):
    """Direção do limiar."""

    MAIOR_QUE = "maior_que"  # padrão: valor alto é pior
    MENOR_QUE = "menor_que"  # valor baixo é pior (nível de congelamento)


@dataclass(frozen=True)
class Criterio:
    """Um teste sobre uma medida da previsão."""

    medida: str
    rotulo: str
    unidade: str
    porque: str
    atencao: float | None = None
    alerta: float | None = None
    valores_aceitos: tuple[int, ...] | None = None
    comparacao: Comparacao = Comparacao.MAIOR_QUE

    @property
    def eh_lista(self) -> bool:
        """Critério de pertencimento (código WMO), não de limiar numérico."""
        return self.valores_aceitos is not None

    def avaliar(self, medidas: Medidas, codigos: set[int]) -> Severidade | None:
        """Severidade que este critério atinge, ou None se não for atingido."""
        if self.eh_lista:
            atingiu = bool(codigos & set(self.valores_aceitos or ()))
            return Severidade.ATENCAO if atingiu else None

        valor = getattr(medidas, self.medida, None)
        if valor is None:
            return None

        if self.comparacao is Comparacao.MENOR_QUE:
            if self.alerta is not None and valor <= self.alerta:
                return Severidade.ALERTA
            if self.atencao is not None and valor <= self.atencao:
                return Severidade.ATENCAO
            return None

        if self.alerta is not None and valor >= self.alerta:
            return Severidade.ALERTA
        if self.atencao is not None and valor >= self.atencao:
            return Severidade.ATENCAO
        return None


@dataclass(frozen=True)
class RegraEvento:
    """Como identificar um evento a partir das medidas."""

    tipo: TipoEvento
    combinacao: Combinacao
    criterios: tuple[Criterio, ...]


@dataclass(frozen=True)
class Cenario:
    """Um par evento × apólice que gera notificação, e o que recomendar."""

    evento: TipoEvento
    apolice: TipoApolice
    recomendacao: str


@dataclass(frozen=True)
class Regras:
    """Conjunto completo de regras de negócio."""

    versao: int
    definido_por: str
    eventos: dict[TipoEvento, RegraEvento]
    cenarios: tuple[Cenario, ...]

    def recomendacao(self, evento: TipoEvento, apolice: TipoApolice) -> str | None:
        for c in self.cenarios:
            if c.evento is evento and c.apolice is apolice:
                return c.recomendacao
        return None

    def notifica(self, evento: TipoEvento, apolice: TipoApolice) -> bool:
        return self.recomendacao(evento, apolice) is not None


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def _criterio(dados: dict, evento: str) -> Criterio:
    medida = dados.get("medida")
    if medida not in Medidas.model_fields:
        raise ErroRegras(
            f"evento '{evento}': medida '{medida}' nao existe em Medidas "
            f"(disponiveis: {', '.join(Medidas.model_fields)})"
        )

    aceitos = dados.get("valores_aceitos")
    tem_limiar = dados.get("atencao") is not None or dados.get("alerta") is not None
    if aceitos is None and not tem_limiar:
        raise ErroRegras(
            f"evento '{evento}', medida '{medida}': defina 'atencao'/'alerta' "
            f"ou 'valores_aceitos'"
        )

    try:
        comparacao = Comparacao(dados.get("comparacao", "maior_que"))
    except ValueError as exc:
        raise ErroRegras(
            f"evento '{evento}': comparacao '{dados.get('comparacao')}' invalida "
            f"(use maior_que ou menor_que)"
        ) from exc

    return Criterio(
        medida=medida,
        rotulo=dados.get("rotulo", medida),
        unidade=dados.get("unidade", ""),
        porque=(dados.get("porque") or "").strip(),
        atencao=dados.get("atencao"),
        alerta=dados.get("alerta"),
        valores_aceitos=tuple(aceitos) if aceitos else None,
        comparacao=comparacao,
    )


def carregar_regras(caminho: Path | None = None) -> Regras:
    """Lê e valida `data/regras.yaml`."""
    caminho = caminho or DATA_DIR / "regras.yaml"
    if not caminho.is_file():
        raise ErroRegras(f"arquivo de regras nao encontrado: {caminho}")

    try:
        bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErroRegras(f"YAML invalido em {caminho.name}: {exc}") from exc

    if not isinstance(bruto, dict) or "eventos" not in bruto:
        raise ErroRegras(f"{caminho.name} nao tem a secao 'eventos'")

    eventos: dict[TipoEvento, RegraEvento] = {}
    for nome, dados in (bruto.get("eventos") or {}).items():
        try:
            tipo = TipoEvento(nome)
        except ValueError as exc:
            raise ErroRegras(
                f"evento '{nome}' nao existe no contrato "
                f"(validos: {', '.join(e.value for e in TipoEvento)})"
            ) from exc

        criterios = dados.get("criterios") or []
        if not criterios:
            raise ErroRegras(f"evento '{nome}' sem nenhum criterio")

        try:
            combinacao = Combinacao(dados.get("combinacao", "qualquer"))
        except ValueError as exc:
            raise ErroRegras(
                f"evento '{nome}': combinacao '{dados.get('combinacao')}' invalida "
                f"(use qualquer ou todos)"
            ) from exc

        eventos[tipo] = RegraEvento(
            tipo=tipo,
            combinacao=combinacao,
            criterios=tuple(_criterio(c, nome) for c in criterios),
        )

    cenarios: list[Cenario] = []
    vistos: set[tuple[TipoEvento, TipoApolice]] = set()
    for dados in bruto.get("cenarios") or []:
        try:
            evento = TipoEvento(dados["evento"])
            apolice = TipoApolice(dados["apolice"])
        except (KeyError, ValueError) as exc:
            raise ErroRegras(f"cenario invalido: {dados}") from exc

        if (evento, apolice) in vistos:
            raise ErroRegras(f"cenario duplicado: {evento.value} + {apolice.value}")
        vistos.add((evento, apolice))

        recomendacao = (dados.get("recomendacao") or "").strip()
        if not recomendacao:
            raise ErroRegras(
                f"cenario {evento.value} + {apolice.value} sem recomendacao preventiva"
            )
        cenarios.append(Cenario(evento=evento, apolice=apolice, recomendacao=recomendacao))

    faltando = {e for e, _ in vistos} - set(eventos)
    if faltando:
        raise ErroRegras(
            "cenarios citam eventos sem limiares definidos: "
            + ", ".join(sorted(e.value for e in faltando))
        )

    return Regras(
        versao=int(bruto.get("versao", 1)),
        definido_por=str(bruto.get("definido_por", "(nao informado)")),
        eventos=eventos,
        cenarios=tuple(cenarios),
    )
