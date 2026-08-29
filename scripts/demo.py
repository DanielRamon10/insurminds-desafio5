"""Demonstração por linha de comando — tarefa D.4.

Executa o fluxo completo de ponta a ponta e imprime o resultado em quatro
etapas, na mesma ordem da interface: previsão obtida, eventos detectados,
segurados selecionados e mensagens geradas. Serve de teste de integração
manual e gera as evidências que vão para o relatório (tarefa E.3).

Uso:

    python scripts/demo.py                     # previsão real (Open-Meteo, com cache)
    python scripts/demo.py --cenario granizo   # cenário forçado sob encomenda
    python scripts/demo.py --cenario raio_atencao --cidade "Porto Alegre"
    python scripts/demo.py --listar-cenarios

A redação usa os templates de fallback (`app/agents/templates.py`) enquanto a
tarefa C.2 da frente C não está integrada — as mensagens citam apenas medidas
reais do evento e respeitam o limite do canal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Mensagens com acento no console do Windows sem depender de chcp/UTF-8 global.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# scripts/ não é pacote: garante que a raiz do projeto esteja importável.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.agents.templates import construir_notificacao
from app.clients.open_meteo import ErroColeta, buscar_varias
from app.config import carregar_cidades
from app.domain.cenarios import CENARIOS_FORCADOS, listar_cenarios, previsao_cenario
from app.domain.eventos import classificar_varias
from app.domain.regras import carregar_regras
from app.domain.segurados import carregar_segurados
from app.outbox import CaixaDeSaida


def _etapa(numero: int, titulo: str) -> None:
    print(f"\n{'=' * 62}\nETAPA {numero} - {titulo}\n{'=' * 62}")


def rodar(cenario: str | None, filtro_cidade: str | None) -> int:
    regras = carregar_regras()
    todas = carregar_cidades()
    cidades = [
        c for c in todas
        if filtro_cidade is None or filtro_cidade.lower() in c.nome.lower()
    ]
    if not cidades:
        print(f"Nenhuma cidade encontrada para '{filtro_cidade}'.")
        return 1

    # ------------------------------------------------------------------
    # 1. Previsão obtida
    # ------------------------------------------------------------------
    _etapa(1, "PREVISAO OBTIDA")
    falhas: list[tuple[object, str]] = []
    if cenario:
        tipo, severidade = CENARIOS_FORCADOS[cenario]
        print(
            f"Fonte: cenário forcado '{cenario}' "
            f"({tipo.value}/{severidade.value})\n"
        )
        previsoes = [previsao_cenario(cenario, cidade) for cidade in cidades]
        for p in previsoes:
            print(
                f"  * {p.local:28s} janela {p.inicio:%d/%m %H:%M} -> "
                f"{p.fim:%H:%M}"
            )
    else:
        print("Fonte: Open-Meteo (previsao real, com cache local)\n")
        previsoes, falhas = buscar_varias(cidades)
        for p in previsoes:
            marca_cache = "(cache)" if p.do_cache else ""
            print(f"  * {p.local:28s} {len(p.horas)} horas {marca_cache}")

    if not previsoes:
        print("Nenhuma previsao disponivel - nada a processar.")
        return 1

    # ------------------------------------------------------------------
    # 2. Eventos detectados
    # ------------------------------------------------------------------
    _etapa(2, "EVENTOS DETECTADOS")
    eventos = classificar_varias(previsoes, regras)
    if not eventos:
        print("  (nenhum evento atingiu limiar - silencio tambem e resposta correta)")
    for ev in eventos:
        print(f"  * {ev.tipo.value}/{ev.severidade.value} em {ev.local}")
        if medidas := ev.medidas.preenchidas():
            print(f"      medidas: {medidas}")

    # ------------------------------------------------------------------
    # 3. Segurados selecionados
    # ------------------------------------------------------------------
    _etapa(3, "SEGURADOS SELECIONADOS")
    segurados = carregar_segurados()
    por_local: dict[str, list] = {}
    for s in segurados:
        por_local.setdefault(s.local, []).append(s)

    selecoes: list[tuple] = []
    vistos: set[str] = set()
    for evento in eventos:
        elegiveis = [
            s for s in por_local.get(evento.local, [])
            if evento.atinge(s.tipo_apolice)
            and regras.notifica(evento.tipo, s.tipo_apolice)
        ]
        for s in elegiveis:
            chave = f"{evento.tipo.value}:{evento.severidade.value}:{s.id}"
            if chave in vistos:
                continue
            vistos.add(chave)
            selecoes.append((s, evento))

    if not selecoes:
        print("  (nenhum segurado no alcance dos eventos detectados)")
    for s, evento in selecoes:
        print(
            f"  * {s.id} {s.nome:26s} apolice={s.tipo_apolice.value:10s} "
            f"canal={s.canal.value:5s} ({evento.tipo.value} em {evento.local})"
        )

    # ------------------------------------------------------------------
    # 4. Mensagens geradas + caixa de saída simulada
    # ------------------------------------------------------------------
    _etapa(4, "MENSAGENS GERADAS E CAIXA DE SAIDA")
    caixa = CaixaDeSaida()
    lote = caixa.iniciar_lote()
    contagem = {"simulado": 0, "descartado": 0}

    for s, evento in selecoes:
        notificacao = construir_notificacao(s, evento, regras)
        if notificacao is None:
            continue
        final = caixa.registrar(notificacao)
        contagem[final.status.value] = contagem.get(final.status.value, 0) + 1
        aviso_limite = "" if final.dentro_do_limite() else " (estourou o limite)"
        print(
            f"\n  [{final.canal.value.upper()}] {final.segurado_nome} "
            f"<{final.segurado_id}> - status: {final.status.value}{aviso_limite}"
        )
        print(f"    \"{final.mensagem}\"")
        print(
            f"    regra: {final.regra_acionada} | "
            f"via LLM: {'sim' if final.gerada_por_llm else 'nao'}"
        )

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------
    print(f"\n{'=' * 62}\nRESUMO\n{'=' * 62}")
    print(f"  cidades consultadas : {len(previsoes)} (falhas de coleta: {len(falhas)})")
    print(f"  eventos detectados  : {len(eventos)}")
    print(
        f"  notificacoes        : {contagem.get('simulado', 0)} simuladas, "
        f"{contagem.get('descartado', 0)} descartadas"
    )
    print(f"  registro auditavel  : {lote}")

    if falhas:
        print("\n  Avisos de coleta:")
        for cidade, motivo in falhas:
            print(f"    - {cidade}: {motivo}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstracao ponta a ponta do Desafio 5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cenario",
        choices=listar_cenarios(),
        default=None,
        help="dispara um cenario climatico forcado em vez da previsao real",
    )
    parser.add_argument(
        "--cidade",
        default=None,
        help="filtra as cidades monitoradas por parte do nome",
    )
    parser.add_argument(
        "--listar-cenarios",
        action="store_true",
        help="mostra os cenarios disponiveis e sai",
    )
    argumentos = parser.parse_args()

    if argumentos.listar_cenarios:
        print("Cenarios forcados disponiveis:")
        for nome in listar_cenarios():
            tipo, severidade = CENARIOS_FORCADOS[nome]
            print(f"  {nome:22s} {tipo.value}/{severidade.value}")
        return

    sys.exit(rodar(argumentos.cenario, argumentos.cidade))


if __name__ == "__main__":
    main()
