"""Guardrails da mensagem (C.3):

1) Nenhum número na mensagem pode ser "inventado" pelo LLM — só os que
   vieram de evento.medidas.preenchidas().
2) Respeitar limite de caracteres por canal (usa Notificacao.dentro_do_limite()).
3) Proibir promessa de cobertura/indenização (risco regulatório).
"""

from __future__ import annotations

import re

from ..schemas import EventoClimatico, Notificacao

# termos que sinalizam promessa de cobertura — revisar com quem conhece
# o domínio de seguros (Paulo Henrique / Frente B) antes da entrega final.
TERMOS_PROIBIDOS = [
    r"est[áa]\s+coberto",
    r"cobertura\s+(?:est[áa]\s+)?garantida",
    r"reembolso\s+(?:est[áa]\s+)?garantido",
    r"indeniza[cç][ãa]o\s+(?:est[áa]\s+)?garantida",
    r"voc[êe]\s+receber[áa]",
    r"ser[áa]\s+ressarcido",
    r"fique\s+tranquilo",
]

_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)?")

#: Números seguidos de unidade de tempo ("24 horas", "48h", "2 dias") não são
#: dados climáticos citados pelo LLM — são referência de prazo, sempre
#: aceitável na mensagem. Sem essa exceção, "nas próximas 24 horas" era
#: rejeitado por engano (24 não é nenhuma medida do evento).
_UNIDADE_TEMPO_RE = re.compile(r"^\s*(?:h|hs|horas?|dias?)\b", re.IGNORECASE)


def _numeros_permitidos(evento: EventoClimatico) -> set[str]:
    permitidos: set[str] = set()
    for valor in evento.medidas.preenchidas().values():
        permitidos.add(str(valor))
        try:
            permitidos.add(str(int(float(valor))))
        except (ValueError, TypeError):
            pass
    return permitidos


def _checar_numeros_inventados(mensagem: str, evento: EventoClimatico) -> str | None:
    permitidos = _numeros_permitidos(evento)
    for match in _NUMERO_RE.finditer(mensagem):
        numero = match.group()
        resto = mensagem[match.end():]
        if _UNIDADE_TEMPO_RE.match(resto):
            continue  # referência de prazo ("24 horas", "48h"), não um dado inventado

        candidato = numero.replace(",", ".")
        candidato_int = candidato.split(".")[0]
        if candidato in permitidos or candidato_int in permitidos:
            continue
        return f"numero '{numero}' nao corresponde a nenhuma medida do evento"
    return None


def _checar_promessa_cobertura(mensagem: str) -> str | None:
    texto = mensagem.lower()
    for padrao in TERMOS_PROIBIDOS:
        if re.search(padrao, texto):
            return f"possivel promessa de cobertura (padrao: '{padrao}')"
    return None


def validar_notificacao(notificacao: Notificacao) -> tuple[bool, str | None]:
    """Valida uma Notificacao já montada (mensagem preenchida)."""
    if not notificacao.dentro_do_limite():
        return False, (
            f"mensagem com {len(notificacao.mensagem)} caracteres excede o limite "
            f"do canal {notificacao.canal.value}"
        )

    erro = _checar_numeros_inventados(notificacao.mensagem, notificacao.evento)
    if erro:
        return False, erro

    erro = _checar_promessa_cobertura(notificacao.mensagem)
    if erro:
        return False, erro

    return True, None