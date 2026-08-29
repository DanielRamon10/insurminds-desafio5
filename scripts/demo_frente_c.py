"""Demo/smoke test da Frente C — roda com Segurado e EventoClimatico
mockados, sem depender das Frentes A e B estarem prontas.

Rodar da raiz do projeto:
    python -m scripts.demo_frente_c

Sem GOOGLE_API_KEY (ou a chave do provedor configurado) no ambiente,
cai automaticamente no fallback por template — é o comportamento que
C.4 exige demonstrar.
"""

from datetime import datetime, timedelta

from app.schemas import (
    Canal,
    Cidade,
    EventoClimatico,
    Medidas,
    Segurado,
    Severidade,
    TipoApolice,
    TipoEvento,
)
from app.agents.orchestrator import rodar_com_eventos_mockados

SEGURADOS_MOCK = [
    Segurado(
        id="1", nome="Ana Silva", tipo_apolice=TipoApolice.RESIDENCIAL,
        cidade="São Paulo", uf="SP", latitude=-23.55, longitude=-46.63, canal=Canal.SMS,
    ),
    Segurado(
        id="2", nome="Bruno Costa", tipo_apolice=TipoApolice.AUTOMOTIVA,
        cidade="São Paulo", uf="SP", latitude=-23.55, longitude=-46.63, canal=Canal.PUSH,
    ),
]

_agora = datetime.now()
EVENTOS_MOCK = [
    EventoClimatico(
        cidade="São Paulo", uf="SP",
        tipo=TipoEvento.CHUVA_INTENSA, severidade=Severidade.ALERTA,
        inicio=_agora, fim=_agora + timedelta(hours=24),
        medidas=Medidas(precipitacao_mm_janela=45.0, precipitacao_mm_h=12.0),
    ),
]


def main():
    notificacoes = rodar_com_eventos_mockados(SEGURADOS_MOCK, EVENTOS_MOCK)

    print(f"\n{len(notificacoes)} notificacao(oes) geradas:\n")
    for n in notificacoes:
        print(f"--- {n.segurado_nome} | canal={n.canal.value} | evento={n.evento.tipo.value} "
              f"| via_llm={n.gerada_por_llm}")
        print(f"    regra: {n.regra_acionada}")
        print(f"    {n.mensagem}\n")


if __name__ == "__main__":
    main()
