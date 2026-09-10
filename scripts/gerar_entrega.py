"""Gera o ZIP do código-fonte para a entrega do Desafio 5.

O enunciado pede um "arquivo ZIP contendo todo o código-fonte". Este script
empacota exatamente isso e **recusa a gerar o pacote** se encontrar qualquer
credencial no conteúdo dos arquivos — o repositório é público e a checagem custa
menos que um vazamento.

    python -m scripts.gerar_entrega

Além da varredura de segredos, confere antes de fechar o pacote que a suíte de
testes passa e que os entregáveis obrigatórios estão presentes: o README com
menção à licença MIT, o arquivo LICENSE e a galeria de mensagens.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "Desafio5_Insurminds_grupo_codigo_fonte.zip"

INCLUIR = [
    "app",
    "scripts",
    "tests",
    "data",
    "docs",
    "streamlit_app.py",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "README.md",
    "LICENSE",
]

#: Nunca entram no pacote: credenciais, ambiente virtual, caches e lotes de execução.
EXCLUIR_DIRS = {
    ".venv", "venv", "__pycache__", ".git", ".pytest_cache",
    ".cache", ".workspace", "caixa_de_saida",
}
EXCLUIR_ARQUIVOS = {".env", "secrets.toml"}
#: `.html` fica de fora: em `docs/` é só o intermediário de onde o PDF foi gerado.
EXCLUIR_SUFIXOS = {".pyc", ".pyo", ".zip", ".log", ".html"}

#: Padrões de credencial procurados no conteúdo dos arquivos de texto.
PADROES_SEGREDO = [
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("Google Cloud API key", re.compile(r"\bAQ\.[0-9A-Za-z_\-]{15,}")),
    ("Anthropic", re.compile(r"\bsk-ant-[0-9A-Za-z_\-]{20,}")),
    ("OpenAI", re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z_\-]{32,}")),
    ("GitHub token", re.compile(r"\b(?:ghp_|github_pat_)[0-9A-Za-z_]{30,}")),
    ("AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]

#: Entregáveis que o enunciado exige explicitamente.
OBRIGATORIOS = [
    ("README.md", "instruções de instalação e execução"),
    ("LICENSE", "licença MIT"),
    ("docs/GALERIA_MENSAGENS.md", "exemplos das mensagens geradas"),
    ("data/regras.yaml", "regras de negócio"),
]

TEXTO = {".py", ".md", ".txt", ".yaml", ".yml", ".csv", ".toml", ".json", ".example", ".gitignore"}


def deve_incluir(caminho: Path) -> bool:
    partes = set(caminho.parts)
    if partes & EXCLUIR_DIRS:
        return False
    if caminho.name in EXCLUIR_ARQUIVOS:
        return False
    return caminho.suffix.lower() not in EXCLUIR_SUFIXOS


def reunir() -> list[Path]:
    arquivos: list[Path] = []
    for alvo in INCLUIR:
        caminho = RAIZ / alvo
        if not caminho.exists():
            print(f"  aviso: {alvo} nao existe e sera ignorado")
            continue
        if caminho.is_file():
            arquivos.append(caminho)
            continue
        arquivos += [p for p in caminho.rglob("*") if p.is_file() and deve_incluir(p)]
    return sorted(arquivos)


def procurar_segredos(arquivos: list[Path]) -> list[str]:
    """Varre o conteúdo dos arquivos de texto. Devolve as ocorrências achadas."""
    achados: list[str] = []
    for arquivo in arquivos:
        if arquivo.suffix.lower() not in TEXTO and arquivo.name not in {".gitignore"}:
            continue
        try:
            conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for rotulo, padrao in PADROES_SEGREDO:
            if m := padrao.search(conteudo):
                relativo = arquivo.relative_to(RAIZ)
                achados.append(f"{relativo}: possivel {rotulo} ({m.group()[:12]}...)")
    return achados


def conferir_obrigatorios() -> list[str]:
    faltando = []
    for alvo, motivo in OBRIGATORIOS:
        if not (RAIZ / alvo).is_file():
            faltando.append(f"{alvo} ({motivo})")
    return faltando


def conferir_licenca_no_readme() -> bool:
    """O enunciado exige que o README informe a licença MIT."""
    readme = (RAIZ / "README.md").read_text(encoding="utf-8", errors="ignore").lower()
    return "mit" in readme


def rodar_testes() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=RAIZ, capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"nao foi possivel rodar a suite: {exc}"
    ultima = [l for l in r.stdout.splitlines() if l.strip()]
    return r.returncode == 0, (ultima[-1] if ultima else "(sem saida)")


def main() -> int:
    print("Empacotando o codigo-fonte do Desafio 5\n")

    arquivos = reunir()
    print(f"  {len(arquivos)} arquivos reunidos")

    if faltando := conferir_obrigatorios():
        print("\nABORTADO: entregavel obrigatorio ausente")
        for f in faltando:
            print(f"  - {f}")
        return 1

    if not conferir_licenca_no_readme():
        print("\nABORTADO: o README nao menciona a licenca MIT, exigida pelo enunciado")
        return 1
    print("  entregaveis obrigatorios presentes; README cita a licenca MIT")

    if achados := procurar_segredos(arquivos):
        print("\nABORTADO: credencial encontrada no conteudo dos arquivos")
        for a in achados:
            print(f"  - {a}")
        print("\nRemova a credencial antes de gerar o pacote.")
        return 1
    print("  nenhuma credencial encontrada")

    passou, resumo = rodar_testes()
    if not passou:
        print(f"\nABORTADO: a suite de testes nao passou -> {resumo}")
        return 1
    print(f"  testes: {resumo}")

    if DESTINO.exists():
        DESTINO.unlink()
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in arquivos:
            z.write(arquivo, arquivo.relative_to(RAIZ))

    tamanho = DESTINO.stat().st_size / 1024
    print(f"\nPacote gerado: {DESTINO.name} ({tamanho:.0f} KB, {len(arquivos)} arquivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
