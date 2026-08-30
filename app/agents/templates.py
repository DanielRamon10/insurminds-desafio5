"""Redator por template — o fallback sem LLM da tarefa C.4.

Assume a redação quando o agente redator (C.2) não pode escrever: a API do LLM
fora do ar, a cota do dia estourada, a mensagem reprovada pelo guardrail (C.3),
ou o operador tendo desligado o LLM para a demonstração não depender de rede.
O orquestrador escolhe entre os dois caminhos; nada chama este módulo direto.

Como a mensagem daqui nunca falha, ela é também o piso de qualidade do sistema
e o termo de comparação da galeria E.4: toda mensagem do LLM deveria ficar ao
menos tão específica quanto a que sairia por template.

Guardrails respeitados aqui (espelham os critérios de C.3):

* **Nenhum número inventado** — a mensagem só cita medidas presentes em
  `evento.medidas`, com suas unidades reais.
* **Limite por canal** — o texto é comprimido até caber em `LIMITE_CARACTERES`,
  cortando em fronteira de palavra.
* **Sem promessa de cobertura** — só orientação preventiva, nunca garantia de
  indenização ou cobertura apolice.
"""

from __future__ import annotations

from datetime import datetime

from ..domain.regras import Regras
from ..schemas import (
    Canal,
    EventoClimatico,
    LIMITE_CARACTERES,
    Notificacao,
    Severidade,
    StatusEnvio,
    TipoApolice,
)

#: Rótulo legível de cada evento, para abrir a mensagem.
ROTULO_EVENTO: dict[str, str] = {
    "chuva_intensa": "chuva intensa",
    "raio": "tempestade com raios",
    "vento_forte": "vento forte",
    "granizo": "granizo",
}

#: Rótulo e unidade de cada medida citável. O código WMO fica fora: não significa
#: nada para o segurado.
ROTULO_MEDIDA: dict[str, tuple[str, str]] = {
    "precipitacao_mm_h": ("chuva na hora mais forte", "mm/h"),
    "precipitacao_mm_janela": ("chuva acumulada em 24 h", "mm"),
    "rajada_km_h": ("rajadas de ate", "km/h"),
    "cape_j_kg": ("energia convectiva de", "J/kg"),
    "nivel_congelamento_m": ("altitude de congelamento em", "m"),
}


def _rotulo_severidade(severidade: Severidade) -> str:
    return "ALERTA" if severidade is Severidade.ALERTA else "AVISO"


def _citar_medidas(evento: EventoClimatico) -> str | None:
    """Frases com os números disponíveis — nunca inventados."""
    partes = [
        f"{rotulo} {valor:g} {unidade}"
        for campo, (rotulo, unidade) in ROTULO_MEDIDA.items()
        if (valor := getattr(evento.medidas, campo)) is not None
    ]
    return ", ".join(partes) if partes else None


def _cortar_em_palavra(texto: str, limite: int) -> str:
    """Corta na última fronteira de palavra inteira antes do limite."""
    if len(texto) <= limite:
        return texto
    # A reserva de 8 caracteres garante que o marcador não estoure o limite.
    trecho = texto[: max(limite - 8, 0)].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return f"{trecho} [...]".rstrip()


def compor_mensagem(
    evento: EventoClimatico,
    tipo_apolice: TipoApolice,
    recomendacao: str,
    canal: Canal,
) -> str:
    """Escreve a mensagem no tom do canal, sempre dentro do limite."""
    rotulo = ROTULO_EVENTO.get(evento.tipo.value, evento.tipo.value.replace("_", " "))
    severidade = _rotulo_severidade(evento.severidade)
    medidas = _citar_medidas(evento)

    if canal is Canal.EMAIL:
        linhas = [
            f"{severidade}: {rotulo.capitalize()} previsto para {evento.local} "
            "(proximas 24 horas).",
        ]
        if medidas:
            linhas.append(f"Medidas observadas: {medidas}.")
        linhas.append(f"Orientação preventiva: {recomendacao}")
        mensagem = "\n\n".join(linhas)
        return _cortar_em_palavra(mensagem, LIMITE_CARACTERES[canal])

    # SMS e PUSH: uma frase compacta, recomendado primeiro, número se couber.
    nucleo = f"{severidade}: {rotulo} em {evento.cidade}-{evento.uf}."
    espaco_restante = LIMITE_CARACTERES[canal] - len(nucleo) - 2

    if medidas and espaco_restante > 20:
        bloco_medidas = _cortar_em_palavra(medidas + ".", espaco_restante // 2)
        nucleo += f" {bloco_medidas}"
        espaco_restante = LIMITE_CARACTERES[canal] - len(nucleo) - 2

    bloco_recomendacao = ""
    if espaco_restante > 15:
        bloco_recomendacao = " " + _cortar_em_palavra(recomendacao, espaco_restante)

    mensagem = f"{nucleo}{bloco_recomendacao}"
    if len(mensagem) > LIMITE_CARACTERES[canal]:  # rede de segurança
        mensagem = _cortar_em_palavra(mensagem, LIMITE_CARACTERES[canal])
    return mensagem


def construir_notificacao(
    segurado,
    evento: EventoClimatico,
    regras: Regras,
    momento: datetime | None = None,
):
    """Gera a `Notificacao` deste segurado para este evento, ou `None`.

    Devolve `None` quando a combinação evento × apólice não está nos cenários
    ativos — inclusive raio × automotiva, descartada pela matriz de negócio.
    """
    tipo_apolice = segurado.tipo_apolice
    if not evento.atinge(tipo_apolice):
        return None
    recomendacao = regras.recomendacao(evento.tipo, tipo_apolice)
    if not recomendacao:
        return None

    return Notificacao(
        segurado_id=segurado.id,
        segurado_nome=segurado.nome,
        tipo_apolice=tipo_apolice,
        evento=evento,
        canal=segurado.canal,
        mensagem=compor_mensagem(evento, tipo_apolice, recomendacao, segurado.canal),
        regra_acionada=(
            f"regras.yaml v{regras.versao}: {evento.tipo.value}/"
            f"{evento.severidade.value}"
        ),
        gerada_em=momento or datetime.now(),
        status=StatusEnvio.PENDENTE,
        gerada_por_llm=False,
    )
