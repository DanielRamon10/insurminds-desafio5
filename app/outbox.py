"""Caixa de saída simulada — tarefa D.1.

Nada é enviado de verdade: o enunciado dispensa explicitamente o envio real.
Cada notificação que chega aqui é registrada com destinatário, canal, evento,
mensagem, timestamp e status, deixando um registro auditável de tudo que
"sairia" — em JSONL, um lote por execução.

O status converge com os guardrails da frente C:

* `simulado` — a mensagem respeita o limite de caracteres do canal; passou.
* `descartado` — estourou o limite do canal (uma mensagem seria cortada na
  operadora); o registro fica para auditoria, mas não "sai".
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR
from .schemas import Notificacao, StatusEnvio


class CaixaDeSaida:
    """Registro auditável das notificações geradas por uma execução."""

    def __init__(self, diretorio: Path | None = None) -> None:
        self.diretorio = diretorio or DATA_DIR / "caixa_de_saida"
        self.arquivo: Path | None = None

    # ------------------------------------------------------------------
    # Ciclo de um lote
    # ------------------------------------------------------------------

    def iniciar_lote(self) -> Path:
        """Abre o arquivo JSONL deste lote. Uma execução = um arquivo."""
        self.diretorio.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = self.diretorio / f"lote_{marca}.jsonl"
        contador = 1
        while caminho.exists():  # dois lotes no mesmo segundo não se sobrepõem
            contador += 1
            caminho = self.diretorio / f"lote_{marca}_{contador}.jsonl"
        caminho.touch()
        self.arquivo = caminho
        return caminho

    def registrar(self, notificacao: Notificacao) -> Notificacao:
        """Registra a notificação e devolve-a com o status final."""
        if self.arquivo is None:
            self.iniciar_lote()

        status = (
            StatusEnvio.SIMULADO
            if notificacao.dentro_do_limite()
            else StatusEnvio.DESCARTADO
        )
        registro = {
            **notificacao.model_dump(mode="json"),
            "status": status.value,
            "registrado_em": datetime.now().isoformat(timespec="seconds"),
        }
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

        return notificacao.model_copy(update={"status": status})

    # ------------------------------------------------------------------
    # Leitura para relatório e interface
    # ------------------------------------------------------------------

    def carregar_lote(self) -> list[dict]:
        """Todos os registros já escritos no lote atual."""
        if self.arquivo is None or not self.arquivo.is_file():
            return []
        return ler_registros(self.arquivo)


def ler_registros(arquivo: Path) -> list[dict]:
    """Lê qualquer lote anterior — usado pelo Streamlit e pelo relatório."""
    registros: list[dict] = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            try:
                registros.append(json.loads(linha))
            except json.JSONDecodeError:
                continue  # linha truncada não derruba a leitura do resto
    return registros

