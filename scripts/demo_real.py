"""Demo com dados REAIS: lê data/segurados.csv e data/cidades.csv e
roda o pipeline inteiro batendo na Open-Meteo (e no INMET) de verdade.

Rodar da raiz do projeto:
    python -m scripts.demo_real

Diferente de scripts/demo_frente_c.py (que usa dados mockados), este
faz chamadas de rede reais — pode levar alguns segundos, e depende de
GOOGLE_API_KEY (ou outra) estar configurada no .env para usar o
redator; sem chave, cai no fallback igual.
"""

from app.config import carregar_cidades
from app.agents.carregar_segurados import carregar_segurados
from app.agents.orchestrator import rodar


def main():
    segurados = carregar_segurados()
    cidades = carregar_cidades()

    print(f"Carregados {len(segurados)} segurados e {len(cidades)} cidades.")
    print("Consultando a previsão (pode levar alguns segundos)...\n")

    notificacoes = rodar(segurados, cidades)

    if not notificacoes:
        print("Nenhum evento relevante encontrado agora — nenhuma notificação gerada.")
        print("(isso é uma resposta válida: silêncio também é resposta correta)")
        return

    print(f"{len(notificacoes)} notificacao(oes) geradas:\n")
    for n in notificacoes:
        print(f"--- {n.segurado_nome} | canal={n.canal.value} | evento={n.evento.tipo.value} "
              f"| severidade={n.evento.severidade.value} | via_llm={n.gerada_por_llm}")
        print(f"    regra: {n.regra_acionada}")
        print(f"    {n.mensagem}\n")


if __name__ == "__main__":
    main()
