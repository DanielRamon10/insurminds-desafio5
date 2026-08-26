"""Interface de demonstração — tarefa D.3.

Streamlit mostrando as quatro etapas em sequência — previsão obtida, eventos
detectados, segurados selecionados e mensagens geradas. O fluxo tem que ser
visível, não inferido.

Executar com `streamlit run streamlit_app.py`. Funciona nos dois modos:

* **Cenário forçado** (padrão): clima extremo sob encomenda, sem depender do
  tempo real — é o seguro da apresentação (tarefa D.2).
* **Previsão real**: consulta a Open-Meteo com cache; um dia de céu limpo pode
  sim não gerar evento algum, e isso também é resposta correta.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.agents.templates import construir_notificacao
from app.clients.open_meteo import buscar_varias
from app.config import carregar_cidades
from app.domain.cenarios import CENARIOS_FORCADOS, listar_cenarios, previsao_cenario
from app.domain.eventos import classificar_varias
from app.domain.regras import carregar_regras
from app.domain.segurados import carregar_segurados
from app.outbox import CaixaDeSaida


# ---------------------------------------------------------------------------
# Cabeçalho e controles
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Comunicação Proativa — Desafio 5", layout="wide")

st.title("Comunicação Proativa com o Segurado")
st.caption(
    "Monitora o clima, identifica o risco, decide quem avisar e escreve o aviso "
    "— antes do sinistro. Nenhuma notificação é enviada de verdade."
)

cidades = carregar_cidades()
regras = carregar_regras()
segurados = carregar_segurados()

with st.sidebar:
    st.header("Controles da demonstração")
    modo = st.radio(
        "Fonte dos dados",
        ["Cenário forçado (demo)", "Previsão real (Open-Meteo)"],
        help="O cenário forçado garante evento na apresentação; a previsão real "
             "pode retornar um dia calmo, e silêncio também é resposta correta.",
    )
    cenario = None
    if modo.startswith("Cenário"):
        cenario = st.selectbox("Cenário climático", listar_cenarios())
    selecionadas = st.multiselect(
        "Cidades monitoradas",
        options=[str(c) for c in cidades],
        default=[str(c) for c in cidades[:3]],
    )
    executar = st.button("Executar demonstração", type="primary")
    st.divider()
    st.markdown(f"**Regras:** regras.yaml v{regras.versao} — {regras.definido_por}")
    st.markdown(f"**Segurados na base:** {len(segurados)}")


def _cidade_por_str(rotulo: str):
    nome = rotulo.split("/")[0]
    return next(c for c in cidades if str(c) == rotulo or c.nome == nome)


if executar:
    alvo = [_cidade_por_str(r) for r in selecionadas] or cidades[:3]

    # --- Etapa 1: previsão obtida -----------------------------------------
    with st.spinner("Obtendo previsão..."):
        if cenario:
            tipo_forcado, sev_forcada = CENARIOS_FORCADOS[cenario]
            previsoes = [previsao_cenario(cenario, c) for c in alvo]
            fonte_info = (
                f"cenário forçado '{cenario}' "
                f"({tipo_forcado.value}/{sev_forcada.value})"
            )
        else:
            previsoes, falhas = buscar_varias(alvo)
            fonte_info = "Open-Meteo (previsão real)"

    st.header(f"1 · Previsão obtida  ({fonte_info})")
    if not previsoes:
        st.error("Nenhuma previsão disponível — verifique a rede.")
        st.stop()
    df_previsoes = pd.DataFrame(
        [
            {
                "cidade": p.local,
                "horas": len(p.horas),
                "janela": f"{p.inicio:%d/%m %H:%M} → {p.fim:%H:%M}",
                "fonte": p.fonte,
            }
            for p in previsoes
        ]
    )
    st.dataframe(df_previsoes, hide_index=True)

    # --- Etapa 2: eventos detectados --------------------------------------
    eventos = classificar_varias(previsoes, regras)
    st.header("2 · Eventos detectados")
    st.metric("Eventos identificados", len(eventos))
    if eventos:
        df_eventos = pd.DataFrame(
            [
                {
                    "tipo": ev.tipo.value,
                    "severidade": ev.severidade.value,
                    "local": ev.local,
                    **ev.medidas.preenchidas(),
                }
                for ev in eventos
            ]
        )
        st.dataframe(df_eventos, hide_index=True)
    else:
        st.info("Nenhum limiar atingido nesta janela.")

    # --- Etapa 3: segurados selecionados ----------------------------------
    por_local: dict[str, list] = {}
    for s in segurados:
        por_local.setdefault(s.local, []).append(s)

    selecoes: list[tuple] = []
    vistos: set[str] = set()
    for ev in eventos:
        for s in por_local.get(ev.local, []):
            if ev.atinge(s.tipo_apolice) and regras.notifica(ev.tipo, s.tipo_apolice):
                chave = f"{ev.tipo.value}:{ev.severidade.value}:{s.id}"
                if chave not in vistos:
                    vistos.add(chave)
                    selecoes.append((s, ev))

    st.header("3 · Segurados selecionados")
    st.metric("Notificações a gerar", len(selecoes))
    if selecoes:
        df_selecao = pd.DataFrame(
            [
                {"id": s.id, "nome": s.nome, "apólice": s.tipo_apolice.value,
                 "canal": s.canal.value, "evento": ev.tipo.value}
                for s, ev in selecoes
            ]
        )
        st.dataframe(df_selecao, hide_index=True)
    else:
        st.info("Nenhum segurado no alcance dos eventos detectados.")

    # --- Etapa 4: mensagens geradas + caixa de saída -----------------------
    st.header("4 · Mensagens geradas e caixa de saída simulada")
    caixa = CaixaDeSaida()
    lote = caixa.iniciar_lote()
    finais = []
    for s, ev in selecoes:
        notificacao = construir_notificacao(s, ev, regras)
        if notificacao is not None:
            finais.append(caixa.registrar(notificacao))

    simuladas = sum(1 for n in finais if n.status.value == "simulado")
    descartadas = len(finais) - simuladas
    col1, col2, col3 = st.columns(3)
    col1.metric("Simuladas", simuladas)
    col2.metric("Descartadas (limite de canal)", descartadas)
    col3.metric("Via LLM", sum(1 for n in finais if n.gerada_por_llm))

    for n in finais:
        icone = "✅" if n.status.value == "simulado" else "⚠️"
        with st.expander(
            f"{icone} [{n.canal.value.upper()}] {n.segurado_nome} — "
            f"{n.evento.tipo.value}/{n.evento.severidade.value}"
        ):
            st.write(n.mensagem)
            st.caption(
                f"regra: {n.regra_acionada} · {len(n.mensagem)} caracteres · "
                f"status: {n.status.value}"
            )

    registros = caixa.carregar_lote()
    if registros:
        st.download_button(
            "Baixar registro auditável (JSONL)",
            data=lote.read_text(encoding="utf-8"),
            file_name=lote.name,
            mime="application/json",
        )
else:
    st.info(
        "Configure os controles na barra lateral e clique em "
        "**Executar demonstração**."
    )

