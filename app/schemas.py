"""Contratos de dados que atravessam o sistema — tarefa F0.2.

Estes são os três formatos que ligam as frentes de trabalho:

    Coleta (A)  ->  EventoClimatico  ->  Decisão (B)  ->  Notificacao  ->  Redação (C)
                                             ^
                                         Segurado (B)

Regra de convivência: **nenhuma frente altera este arquivo sozinha.** Mudar um
campo aqui quebra o trabalho de outra pessoa; qualquer alteração passa por
acordo do grupo e por PR.

Decisões embutidas que o grupo deve validar:

1. **Janela agregada, não hora a hora.** A API devolve 72 valores horários por
   cidade. Um `EventoClimatico` representa uma *janela* (padrão: próximas 24 h),
   porque é isso que gera mensagem útil ao segurado — "nas próximas 24 horas há
   previsão de..." — e evita 72 eventos por cidade.

2. **Uma apólice por segurado.** Simplifica o motor de regras sem perda didática.

3. **Duas severidades.** `ATENCAO` e `ALERTA` permitem tom e urgência diferentes
   na mensagem sem dobrar a complexidade das regras.

4. **As medidas viajam com o evento.** `Medidas` carrega os números que
   dispararam a classificação, para a mensagem citar valor real e o relatório
   poder auditar cada decisão.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Vocabulário fechado
# ---------------------------------------------------------------------------


class TipoApolice(str, Enum):
    """Tipos de apólice cobertos pela solução."""

    RESIDENCIAL = "residencial"
    AUTOMOTIVA = "automotiva"


class TipoEvento(str, Enum):
    """Eventos climáticos monitorados."""

    CHUVA_INTENSA = "chuva_intensa"
    RAIO = "raio"
    VENTO_FORTE = "vento_forte"
    GRANIZO = "granizo"


class Severidade(str, Enum):
    """Grau do evento. Define o tom e a urgência da mensagem."""

    ATENCAO = "atencao"
    ALERTA = "alerta"


class Canal(str, Enum):
    """Canal de comunicação. O envio é sempre simulado."""

    SMS = "sms"
    EMAIL = "email"
    PUSH = "push"


#: Limite de caracteres por canal, aplicado nos guardrails da tarefa C.3.
LIMITE_CARACTERES: dict[Canal, int] = {
    Canal.SMS: 160,
    Canal.PUSH: 240,
    Canal.EMAIL: 2000,
}

#: Combinações evento × apólice que geram notificação (matriz da tarefa F0.1).
#: Raio × automotiva fica de fora: um automóvel é uma gaiola de Faraday e não há
#: recomendação preventiva honesta a dar nesse caso.
CENARIOS_ATIVOS: set[tuple[TipoEvento, TipoApolice]] = {
    (TipoEvento.CHUVA_INTENSA, TipoApolice.RESIDENCIAL),
    (TipoEvento.CHUVA_INTENSA, TipoApolice.AUTOMOTIVA),
    (TipoEvento.RAIO, TipoApolice.RESIDENCIAL),
    (TipoEvento.VENTO_FORTE, TipoApolice.RESIDENCIAL),
    (TipoEvento.VENTO_FORTE, TipoApolice.AUTOMOTIVA),
    (TipoEvento.GRANIZO, TipoApolice.RESIDENCIAL),
    (TipoEvento.GRANIZO, TipoApolice.AUTOMOTIVA),
}


# ---------------------------------------------------------------------------
# Localização
# ---------------------------------------------------------------------------


class Cidade(BaseModel):
    """Cidade monitorada. Coordenadas reais — a API precisa delas."""

    nome: str
    uf: str = Field(min_length=2, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, v: str) -> str:
        return v.upper()

    def __str__(self) -> str:
        return f"{self.nome}/{self.uf}"


# ---------------------------------------------------------------------------
# Contrato 1 — Segurado
# ---------------------------------------------------------------------------


class Segurado(BaseModel):
    """Segurado fictício. Dados pessoais são sintéticos; a cidade é real."""

    id: str
    nome: str
    tipo_apolice: TipoApolice
    cidade: str
    uf: str = Field(min_length=2, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    canal: Canal

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, v: str) -> str:
        return v.upper()

    @property
    def local(self) -> str:
        return f"{self.cidade}/{self.uf}"


# ---------------------------------------------------------------------------
# Contrato 2 — EventoClimatico
# ---------------------------------------------------------------------------


class Medidas(BaseModel):
    """Números que sustentam a classificação do evento.

    Todos opcionais: cada tipo de evento preenche os que usa. A mensagem só pode
    citar valores presentes aqui — é o que impede o LLM de inventar número.
    """

    precipitacao_mm_h: float | None = None
    precipitacao_mm_janela: float | None = None
    rajada_km_h: float | None = None
    cape_j_kg: float | None = None
    nivel_congelamento_m: float | None = None
    codigo_wmo: int | None = None

    def preenchidas(self) -> dict[str, float | int]:
        """Apenas as medidas efetivamente disponíveis."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class EventoClimatico(BaseModel):
    """Evento identificado para uma cidade, numa janela de tempo.

    Representa a janela inteira (padrão: 24 h), não uma hora isolada.
    """

    cidade: str
    uf: str = Field(min_length=2, max_length=2)
    tipo: TipoEvento
    severidade: Severidade
    inicio: datetime
    fim: datetime
    medidas: Medidas
    fonte: str = "open-meteo"

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, v: str) -> str:
        return v.upper()

    @field_validator("fim")
    @classmethod
    def _fim_depois_do_inicio(cls, v: datetime, info) -> datetime:
        inicio = info.data.get("inicio")
        if inicio is not None and v <= inicio:
            raise ValueError("fim deve ser posterior a inicio")
        return v

    @property
    def local(self) -> str:
        return f"{self.cidade}/{self.uf}"

    def atinge(self, apolice: TipoApolice) -> bool:
        """Se este evento é relevante para o tipo de apólice informado."""
        return (self.tipo, apolice) in CENARIOS_ATIVOS


# ---------------------------------------------------------------------------
# Contrato 3 — Notificacao
# ---------------------------------------------------------------------------


class StatusEnvio(str, Enum):
    """Estado da notificação na caixa de saída simulada."""

    PENDENTE = "pendente"
    SIMULADO = "simulado"
    DESCARTADO = "descartado"


class Notificacao(BaseModel):
    """Comunicação gerada para um segurado. Nunca enviada de verdade."""

    segurado_id: str
    segurado_nome: str
    tipo_apolice: TipoApolice
    evento: EventoClimatico
    canal: Canal
    mensagem: str
    regra_acionada: str
    gerada_em: datetime
    status: StatusEnvio = StatusEnvio.PENDENTE
    gerada_por_llm: bool = True

    @field_validator("mensagem")
    @classmethod
    def _mensagem_nao_vazia(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("mensagem nao pode ser vazia")
        return v.strip()

    def dentro_do_limite(self) -> bool:
        """Se a mensagem respeita o limite de caracteres do canal."""
        return len(self.mensagem) <= LIMITE_CARACTERES[self.canal]
