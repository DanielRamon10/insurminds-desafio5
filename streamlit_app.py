"""Interface de demonstração — tarefa D.3.

Streamlit mostrando as quatro etapas em sequência — previsão obtida, eventos
detectados, segurados selecionados e mensagens geradas. O fluxo tem que ser
visível, não inferido.

Executar com `streamlit run streamlit_app.py`. Funciona nos dois modos:

* **Cenário forçado** (padrão): clima extremo sob encomenda, sem depender do
  tempo real — é o seguro da apresentação (tarefa D.2).
* **Previsão real**: consulta a Open-Meteo com cache; um dia de céu limpo pode
  sim não gerar evento algum, e isso também é resposta correta.

Camada visual: tudo é nativo do Streamlit — tema definido em
`.streamlit/config.toml` e CSS injetado no topo do app (hero, badges e cartões).
Nenhuma dependência extra além das já listadas no `requirements.txt`.
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
# Camada visual — tema (config.toml) + CSS injetado em duas partes
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Comunicação Proativa — Desafio 5",
    page_icon="⛈️",
    layout="wide",
)

CSS = """
<style>
/* ---------- sidebar: navy profundo, casa com o hero ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0B2545 0%, #12365F 100%);
}
[data-testid="stSidebar"] * { color: #E7EEF7; }
[data-testid="stSidebar"] hr { border-color: rgba(231,238,247,.25) !important; }

/* ---------- botões ---------- */
.stButton > button {
    border-radius: 999px; font-weight: 700; padding: .5rem 1rem;
    box-shadow: 0 6px 16px rgba(47,111,237,.30);
}
.stDownloadButton > button { border-radius: 999px; }

/* ---------- hero ---------- */
.hero {
    display: flex; align-items: center; gap: 18px;
    background:
        radial-gradient(1200px 300px at 85% -40%, rgba(56,189,248,.35), transparent),
        linear-gradient(135deg, #0B2545 0%, #134074 55%, #1C6DA8 100%);
    border-radius: 18px; padding: 26px 32px; margin-bottom: 6px;
}
.hero-icon { font-size: 52px; line-height: 1; filter: drop-shadow(0 3px 8px rgba(0,0,0,.35)); }
.hero h1 { color:#FFF; font-size:1.7rem; font-weight:800; margin:0 0 6px 0; letter-spacing:-.02em; }
.hero p { color:#C9DCF2; margin:0; font-size:.95rem; }
.hero b { color:#FFF; }

/* ---------- cabeçalho de etapa ---------- */
.etapa { display:flex; align-items:center; gap:14px; margin:30px 0 12px 0; }
.etapa-num {
    flex:none; width:38px; height:38px; border-radius:12px;
    background:linear-gradient(135deg,#2F6FED,#1C6DA8); color:#fff;
    font-weight:800; font-size:19px; display:flex;
    align-items:center; justify-content:center;
    box-shadow:0 4px 10px rgba(47,111,237,.35);
}
.etapa-titulo { font-size:1.15rem !important; font-weight:700 !important; margin:0 !important; }
.etapa-sub { color:#64748B; font-size:.83rem; margin-top:2px; display:block; }

/* ---------- pills (badges) ---------- */
.pill {
    display:inline-block; padding:3px 11px; border-radius:999px;
    font-size:.72rem; font-weight:700; letter-spacing:.03em;
    text-transform:uppercase; margin-right:6px; vertical-align:middle;
    border:1px solid transparent; white-space:nowrap;
}
.pill-alerta   { background:#FEE2E2; color:#B91C1C; border-color:#FCA5A5; }
.pill-atencao  { background:#FEF3C7; color:#B45309; border-color:#FCD34D; }
.pill-sms      { background:#DBEAFE; color:#1D4ED8; border-color:#93C5FD; }
.pill-push     { background:#DCFCE7; color:#15803D; border-color:#86EFAC; }
.pill-email    { background:#EDE9FE; color:#6D28D9; border-color:#C4B5FD; }
.pill-status-ok  { background:#ECFDF5; color:#047857; border-color:#A7F3D0; }
.pill-status-off { background:#FFF7ED; color:#C2410C; border-color:#FDBA74; }
.pill-apolice  { background:#F1F5FB; color:#334155; border-color:#CBD5E1; }

/* ---------- cartões de métrica ---------- */
.card-metric {
    background:#FFF; border:1px solid #E2E8F0; border-radius:14px;
    padding:18px 22px; text-align:center; height:100%;
    box-shadow:0 1px 3px rgba(15,36,57,.06);
    transition:transform .15s ease, box-shadow .15s ease;
}
.card-metric:hover { transform:translateY(-2px); box-shadow:0 8px 20px rgba(15,36,57,.10); }
.metric-val { font-size:32px; font-weight:800; line-height:1.15; letter-spacing:-.02em; }
.metric-lab {
    color:#64748B; font-size:.78rem; font-weight:600;
    text-transform:uppercase; letter-spacing:.05em; margin-top:4px;
}

/* ---------- balão da mensagem ---------- */
.msg {
    background:#F8FAFC; border-left:4px solid #2F6FED; border-radius:10px;
    padding:14px 18px; margin-bottom:10px; font-size:.95rem;
    line-height:1.55; white-space:pre-wrap;
}

/* ---------- detalhes finos ---------- */
[data-testid="stExpander"] { border-radius:12px !important; overflow:hidden; }
[data-testid="stExpander"] summary strong { font-weight:600; }
.disclaimer {
    color:#64748B; font-size:.82rem; text-align:center; margin-top:34px;
    padding-top:14px; border-top:1px solid #EEF2F7;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Ícones e classes auxiliares por valor de enum do schemas.py
ICONE_EVENTO = {"chuva_intensa": "🌧️", "raio": "⚡", "vento_forte": "💨", "granizo": "🧊"}
PILL_SEVERIDADE = {"atencao": ("pill-atencao", "atenção"), "alerta": ("pill-alerta", "alerta")}
PILL_CANAL = {"sms": "pill-sms", "push": "pill-push", "email": "pill-email"}


def _pill(texto: str, classe: str) -> str:
    return f'<span class="pill {classe}">{texto}</span>'


def _cabecalho_etapa(numero: int, titulo: str, subtitulo: str = "") -> None:
    sub = f'<span class="etapa-sub">{subtitulo}</span>' if subtitulo else ""
    st.markdown(
        f'<div class="etapa"><div class="etapa-num">{numero}</div>'
        f"<div><p class=\"etapa-titulo\">{titulo}</p>{sub}</div></div>",
        unsafe_allow_html=True,
    )


def _cartao(valor, rotulo: str, cor: str) -> str:
    return (
        f'<div class="card-metric"><div class="metric-val" style="color:{cor}">{valor}</div>'
        f'<div class="metric-lab">{rotulo}</div></div>'
    )


def _linha_evento(tipo: str, severidade: str) -> str:
    sev_classe, sev_rotulo = PILL_SEVERIDADE.get(severidade, ("pill-apolice", severidade))
    return (
        f"{ICONE_EVENTO.get(tipo, '🌩️')} {_pill(sev_rotulo, sev_classe)} "
        f"<b style='font-size:.92rem'>{tipo.replace('_', ' ')}</b>"
    )


# ---------------------------------------------------------------------------
# Cabeçalho e controles
# ---------------------------------------------------------------------------

st.markdown(
    """<div class="hero"><div class="hero-icon">⛈️</div><div>
<h1>Comunicação Proativa com o Segurado</h1>
<p>Monitora o clima · identifica o risco · decide quem avisar · escreve o aviso
— <b>antes do sinistro acontecer</b>.</p>
</div></div>""",
    unsafe_allow_html=True,
)
st.caption("🛡️ **Ambiente de demonstração** — nenhuma notificação é enviada de verdade.")

cidades = carregar_cidades()
regras = carregar_regras()
segurados = carregar_segurados()

with st.sidebar:
    st.markdown("## 🎛️ Controles\nDemonstração guiada")
    modo = st.radio(
        "Fonte dos dados",
        ["Cenário forçado (demo)", "Previsão real (Open-Meteo)"],
        help="O cenário forçado garante evento na apresentação; a previsão real "
             "pode retornar um dia calmo, e silêncio também é resposta correta.",
        label_visibility="collapsed",
    )
    cenario = None
    if modo.startswith("Cenário"):
        cenario = st.selectbox("Cenário climático", listar_cenarios())
    selecionadas = st.multiselect(
        "Cidades monitoradas",
        options=[str(c) for c in cidades],
        default=[str(c) for c in cidades[:3]],
    )
    executar = st.button("⚡ Executar demonstração", type="primary", use_container_width=True)
    st.divider()
    st.caption(f"**Regras:** regras.yaml v{regras.versao}")
    st.caption(f"Definidas por {regras.definido_por}")
    st.caption(f"👥 {len(segurados)} segurados na base")

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

    _cabecalho_etapa(
        1, "Previsão obtida", f"{len(previsoes)} cidade(s) · fonte: {fonte_info}"
    )
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
    _cabecalho_etapa(2, "Eventos detectados", "classificados pelos limiares de regras.yaml")
    if eventos:
        st.markdown(
            "<div>"
            + "</div>".join(
                f'<div style="margin-bottom:6px">{_linha_evento(ev.tipo.value, ev.severidade.value)}</div>'
                for ev in eventos
            )
            + "</div>",
            unsafe_allow_html=True,
        )
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
        st.info("☀️ Nenhum limiar atingido nesta janela. Silêncio também é resposta correta.")

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

    _cabecalho_etapa(3, "Segurados selecionados", "cruzamento evento × apólice × local")
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
    _cabecalho_etapa(
        4, "Mensagens geradas e caixa de saída simulada",
        "registro auditável em JSONL — nada sai de verdade",
    )
    caixa = CaixaDeSaida()
    lote = caixa.iniciar_lote()
    finais = []
    for s, ev in selecoes:
        notificacao = construir_notificacao(s, ev, regras)
        if notificacao is not None:
            finais.append(caixa.registrar(notificacao))

    simuladas = sum(1 for n in finais if n.status.value == "simulado")
    descartadas = len(finais) - simuladas
    via_llm = sum(1 for n in finais if n.gerada_por_llm)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(_cartao(simuladas, "simuladas", "#047857"), unsafe_allow_html=True)
    with col2:
        st.markdown(_cartao(descartadas, "descartadas (limite)", "#C2410C"), unsafe_allow_html=True)
    with col3:
        st.markdown(_cartao(via_llm, "via LLM", "#2F6FED"), unsafe_allow_html=True)

    for n in finais:
        icone = ICONE_EVENTO.get(n.evento.tipo.value, "🌩️")
        sev_classe, sev_rotulo = PILL_SEVERIDADE.get(
            n.evento.severidade.value, ("pill-apolice", n.evento.severidade.value)
        )
        canal_classe = PILL_CANAL.get(n.canal.value, "pill-apolice")
        status_classe = (
            "pill-status-ok" if n.status.value == "simulado" else "pill-status-off"
        )
        cabecalho = (
            f"{icone} &nbsp;<strong>{n.segurado_nome}</strong>"
            f"&nbsp;&nbsp;{_pill(n.canal.value.upper(), canal_classe)}"
            f"{_pill(sev_rotulo, sev_classe)}"
        )
        with st.expander(cabecalho):
            st.markdown(f'<div class="msg">{n.mensagem}</div>', unsafe_allow_html=True)
            st.caption(
                f"regra: `{n.regra_acionada}` · {len(n.mensagem)} caracteres · "
                f"status: {_pill(n.status.value, status_classe)}"
            )

    registros = caixa.carregar_lote()
    if registros:
        st.download_button(
            "⬇️ Baixar registro auditável (JSONL)",
            data=lote.read_text(encoding="utf-8"),
            file_name=lote.name,
            mime="application/json",
        )
else:
    st.markdown(
        '<div class="msg" style="text-align:center; border-left:none; '
        'border-top:4px solid #2F6FED;">Configure os controles na barra lateral '
        "e clique em <b>⚡ Executar demonstração</b>.</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    '<p class="disclaimer">Desafio 5 — InsurMinds / I2A2 · frente D: simulação '
    "de envio e demonstração · nenhuma mensagem deixa este ambiente</p>",
    unsafe_allow_html=True,
)





