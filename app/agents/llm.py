"""Cliente de LLM para a Frente C — usa o ConfigLLM/obter_api_key já
existentes em app/config.py (F0.4), não reinventa leitura de chave.

Reaproveita a lista `modelos` de cada provedor em PROVEDORES: se o
modelo padrão estourar cota, tenta o próximo da lista antes de desistir
e acionar o fallback por template (C.4).
"""

from __future__ import annotations

import concurrent.futures
import os
import socket

from ..config import ConfigLLM, PROVEDORES, obter_api_key

#: Sem timeout, uma rede lenta/instável trava a chamada indefinidamente
#: em vez de cair no fallback (C.4) — é exatamente o cenário que o
#: fallback existe para cobrir. O parâmetro `timeout` das libs
#: (langchain-google-genai etc.) nem sempre é respeitado quando a
#: conexão trava no nível do socket/SSL (firewall/antivírus filtrando
#: silenciosamente, por exemplo), então forçamos por fora com uma
#: thread separada — isso SEMPRE desiste no tempo certo.
TIMEOUT_SEGUNDOS = 20

#: Algumas redes têm IPv6 mal configurado: a conexão abre normalmente
#: mas os dados nunca chegam (trava em silêncio, em vez de dar erro).
#: Forçar IPv4 evita isso. Desative com FORCAR_IPV4=0 no .env se a sua
#: rede não tiver esse problema.
if os.environ.get("FORCAR_IPV4", "1") != "0":
    _getaddrinfo_original = socket.getaddrinfo

    def _getaddrinfo_apenas_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo_apenas_ipv4


class LLMIndisponivel(Exception):
    """Levantada quando nenhuma chave/modelo funciona. O orquestrador
    captura isso e cai no AgenteFallback (C.4)."""


#: Depois do primeiro timeout de rede nesta execução, não adianta
#: tentar de novo nas próximas notificações — a rede não vai consertar
#: sozinha no meio do processamento. Evita esperar TIMEOUT_SEGUNDOS a
#: cada um dos N segurados quando a causa é a mesma pra todos.
_rede_marcada_indisponivel = False


class TimeoutRede(LLMIndisponivel):
    """Timeout por falha de rede — tentar outro modelo não ajuda, já
    que todos usam a mesma conexão. Levantar isso interrompe o loop de
    candidatos imediatamente, em vez de esperar o timeout de novo para
    cada modelo da lista."""


def _extrair_texto(conteudo) -> str:
    """`resposta.content` normalmente é string, mas versões recentes do
    LangChain/Gemini podem devolver uma lista de partes (ex: quando o
    modelo usa "thinking" ou resposta multimodal). Sem isso, `.strip()`
    numa lista quebra com AttributeError, tratado como falha genérica —
    o que faz a galeria inteira cair no template mesmo com a chave
    funcionando."""
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, list):
        partes = []
        for item in conteudo:
            if isinstance(item, str):
                partes.append(item)
            elif isinstance(item, dict):
                texto = item.get("text") or item.get("content")
                if texto:
                    partes.append(str(texto))
        return "".join(partes).strip()
    return str(conteudo or "").strip()


def _montar_chat_model(provedor: str, modelo: str, api_key: str):
    if provedor == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=modelo, google_api_key=api_key, temperature=0.4,
            timeout=TIMEOUT_SEGUNDOS, max_retries=1,
        )
    if provedor == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=modelo, api_key=api_key, temperature=0.4,
            timeout=TIMEOUT_SEGUNDOS,
        )
    if provedor == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=modelo, api_key=api_key, temperature=0.4,
            timeout=TIMEOUT_SEGUNDOS,
        )
    raise LLMIndisponivel(f"Provedor '{provedor}' nao suportado")


def _invocar_com_timeout(chat, prompt: str, timeout_segundos: int):
    """chat.invoke() numa thread separada, com prazo de verdade.

    Necessário porque o parâmetro `timeout` das libs de LLM às vezes
    não é respeitado quando a conexão trava no nível do socket (ex:
    firewall/antivírus descartando pacotes silenciosamente em vez de
    recusar a conexão). A thread trava sozinha em segundo plano, mas o
    fluxo principal segue — o que importa é nunca deixar o pipeline
    esperando pra sempre.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futuro = executor.submit(chat.invoke, prompt)
        try:
            return futuro.result(timeout=timeout_segundos)
        except concurrent.futures.TimeoutError as e:
            raise TimeoutRede(
                f"sem resposta em {timeout_segundos}s — provável bloqueio de rede/firewall"
            ) from e


def gerar_texto(prompt: str, cfg: ConfigLLM | None = None) -> str:
    """Tenta o modelo configurado; se falhar (cota, erro de rede, etc.),
    tenta os demais modelos do mesmo provedor antes de desistir.
    """
    global _rede_marcada_indisponivel

    if _rede_marcada_indisponivel:
        raise LLMIndisponivel(
            "rede marcada como indisponível nesta execução (timeout já ocorreu antes)"
        )

    cfg = cfg or ConfigLLM()
    api_key = obter_api_key(cfg.provedor)
    if not api_key:
        raise LLMIndisponivel(f"{cfg.env_key} nao configurada no .env")

    candidatos = [cfg.modelo] + [
        m for m in PROVEDORES[cfg.provedor]["modelos"] if m != cfg.modelo
    ]

    ultimo_erro: Exception | None = None
    for modelo in candidatos:
        try:
            chat = _montar_chat_model(cfg.provedor, modelo, api_key)
            resposta = _invocar_com_timeout(chat, prompt, TIMEOUT_SEGUNDOS)
            texto = _extrair_texto(resposta.content)
            if texto:
                return texto
        except TimeoutRede:
            # rede indisponível — os outros modelos usariam a mesma
            # conexão, então tentar de novo só multiplicaria a espera
            # sem chance real de sucesso. Marca pra esta execução
            # inteira já pular direto pro fallback.
            _rede_marcada_indisponivel = True
            raise
        except ImportError as e:
            raise LLMIndisponivel(
                f"Instale o pacote do provedor: {PROVEDORES[cfg.provedor]['pacote']}"
            ) from e
        except Exception as e:  # cota estourada, erro da API, etc.
            ultimo_erro = e
            continue

    raise LLMIndisponivel(f"Todos os modelos de '{cfg.provedor}' falharam: {ultimo_erro}")
