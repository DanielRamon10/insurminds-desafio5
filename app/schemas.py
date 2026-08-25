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

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

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
    #: Código IBGE do município. Usado para casar alertas oficiais do INMET por
    #: identificador, e não por nome — "Santos" casaria com "Santos Dumont".
    codigo_ibge: str | None = None

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
    #: Avisos oficiais vigentes para a mesma cidade e janela, quando houver.
    #: Corroboram a classificação própria; não a substituem.
    alertas_oficiais: list[AlertaOficial] = Field(default_factory=list)

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
# Ponte entre coleta e análise (frente A -> frente B)
#
# A previsão bruta não é um evento: é a série horária de onde os eventos são
# extraídos. Fica aqui, e não dentro do cliente, porque é a interface entre duas
# frentes — quem classifica não precisa saber de qual API o dado veio.
# ---------------------------------------------------------------------------


class PrevisaoHoraria(BaseModel):
    """Série horária de uma cidade, já normalizada e com unidades conhecidas.

    As listas são paralelas: o índice i de cada uma corresponde a `horas[i]`.
    Valores ausentes viram `None` em vez de zero — zero é uma medição válida e
    confundir os dois falsearia a classificação.
    """

    cidade: str
    uf: str = Field(min_length=2, max_length=2)
    horas: list[datetime]
    precipitacao_mm: list[float | None]
    rajada_km_h: list[float | None]
    codigo_wmo: list[int | None]
    cape_j_kg: list[float | None]
    nivel_congelamento_m: list[float | None]
    fonte: str = "open-meteo"
    do_cache: bool = False

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _series_do_mesmo_tamanho(self) -> "PrevisaoHoraria":
        n = len(self.horas)
        for campo in (
            "precipitacao_mm", "rajada_km_h", "codigo_wmo",
            "cape_j_kg", "nivel_congelamento_m",
        ):
            if len(getattr(self, campo)) != n:
                raise ValueError(f"{campo} tem tamanho diferente de horas ({n})")
        if n == 0:
            raise ValueError("previsao sem nenhuma hora")
        return self

    @property
    def local(self) -> str:
        return f"{self.cidade}/{self.uf}"

    @property
    def inicio(self) -> datetime:
        return self.horas[0]

    @property
    def fim(self) -> datetime:
        """Fim da janela: o término da última hora, não o seu início.

        A série horária rotula cada valor pelo início da hora — "às 12h choveu
        X" cobre de 12h a 13h. Sem somar essa hora, uma previsão de um único
        ponto teria janela de duração zero.
        """
        return self.horas[-1] + timedelta(hours=1)

    def agregar(self) -> Medidas:
        """Condensa a janela inteira nas medidas que as regras avaliam.

        Chuva acumulada soma; as demais tomam o pior valor da janela — exceto o
        nível de congelamento, onde o pior caso é o MENOR valor (quanto mais
        baixa a isoterma de 0 °C, maior a chance de o granizo chegar ao solo).
        """
        def maior(valores: list[float | None]) -> float | None:
            presentes = [v for v in valores if v is not None]
            return max(presentes) if presentes else None

        def menor(valores: list[float | None]) -> float | None:
            presentes = [v for v in valores if v is not None]
            return min(presentes) if presentes else None

        chuva = [v for v in self.precipitacao_mm if v is not None]
        codigos = [c for c in self.codigo_wmo if c is not None]

        return Medidas(
            precipitacao_mm_h=maior(self.precipitacao_mm),
            precipitacao_mm_janela=round(sum(chuva), 1) if chuva else None,
            rajada_km_h=maior(self.rajada_km_h),
            cape_j_kg=maior(self.cape_j_kg),
            nivel_congelamento_m=menor(self.nivel_congelamento_m),
            codigo_wmo=max(codigos) if codigos else None,
        )

    def codigos_presentes(self) -> set[int]:
        """Todos os códigos WMO da janela — usado por critérios de lista."""
        return {c for c in self.codigo_wmo if c is not None}


# ---------------------------------------------------------------------------
# Segunda fonte: alertas oficiais
#
# Natureza diferente da previsão numérica: aqui o órgão oficial já decidiu que
# há risco e publicou o aviso. Não substitui a classificação própria — serve de
# corroboração, e o texto oficial enriquece a mensagem.
# ---------------------------------------------------------------------------


class AlertaOficial(BaseModel):
    """Aviso meteorológico emitido por órgão oficial (INMET)."""

    id: str
    titulo: str                     # "Tempestade", "Baixa Umidade"
    severidade: str                 # "Perigo", "Perigo Potencial"
    inicio: datetime
    fim: datetime
    riscos: list[str] = Field(default_factory=list)
    instrucoes: list[str] = Field(default_factory=list)
    codigos_ibge: set[str] = Field(default_factory=set)
    fonte: str = "inmet"

    def cobre(self, cidade: Cidade) -> bool:
        """Se este aviso vale para a cidade, casando por código IBGE."""
        return bool(cidade.codigo_ibge) and cidade.codigo_ibge in self.codigos_ibge

    def vigente_em(self, momento: datetime) -> bool:
        return self.inicio <= momento <= self.fim


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
