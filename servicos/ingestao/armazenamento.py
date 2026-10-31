"""
Persistencia do indice vetorial em disco (TAREFA 1).

Arquivos em DIR_DADOS (volume compartilhado entre a API e o worker):
  indice.json               -> versao, documentos, trechos e seus vetores
  vetorizador-v{N}.joblib   -> o TF-IDF ajustado na versao N

Escrita atomica: grava em arquivo temporario e troca com os.replace(), entao
quem le nunca ve um arquivo pela metade. O vetorizador e gravado ANTES do
indice.json, e o indice aponta para o arquivo da sua versao - assim indice e
vocabulario sempre combinam.
"""
import glob
import json
import os
import re
import threading

import joblib

DIR_DADOS = os.getenv("DIR_DADOS", "dados")
ARQ_INDICE = os.path.join(DIR_DADOS, "indice.json")
TAMANHO_TRECHO = int(os.getenv("TAMANHO_TRECHO", "500"))

INDICE_VAZIO = {"versao": 0, "documentos": {}, "trechos": [], "vetorizador": None}


def quebrar_em_trechos(texto, tamanho=TAMANHO_TRECHO):
    """Divide o texto em paragrafos; paragrafos longos viram grupos de frases."""
    trechos = []
    for paragrafo in re.split(r"\n\s*\n", texto.strip()):
        paragrafo = " ".join(paragrafo.split())
        if not paragrafo:
            continue
        if len(paragrafo) <= tamanho:
            trechos.append(paragrafo)
            continue
        atual = ""
        for frase in re.split(r"(?<=[.!?])\s+", paragrafo):
            if atual and len(atual) + len(frase) + 1 > tamanho:
                trechos.append(atual)
                atual = frase
            else:
                atual = f"{atual} {frase}".strip()
        if atual:
            trechos.append(atual)
    return trechos


def _gravar_atomico(caminho, escrever):
    tmp = f"{caminho}.tmp-{os.getpid()}"
    escrever(tmp)
    os.replace(tmp, caminho)


def salvar(indice, vetorizador):
    os.makedirs(DIR_DADOS, exist_ok=True)
    nome_vet = f"vetorizador-v{indice['versao']}.joblib"
    _gravar_atomico(os.path.join(DIR_DADOS, nome_vet),
                    lambda tmp: joblib.dump(vetorizador, tmp))
    indice = {**indice, "vetorizador": nome_vet}

    def escrever_json(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False)
    _gravar_atomico(ARQ_INDICE, escrever_json)

    # mantem so as duas ultimas versoes do vetorizador
    antigos = sorted(glob.glob(os.path.join(DIR_DADOS, "vetorizador-v*.joblib")),
                     key=os.path.getmtime)
    for caminho in antigos[:-2]:
        try:
            os.remove(caminho)
        except OSError:
            pass


def carregar():
    """Devolve (indice, vetorizador). Indice vazio se ainda nao existir."""
    if not os.path.exists(ARQ_INDICE):
        return dict(INDICE_VAZIO), None
    with open(ARQ_INDICE, encoding="utf-8") as f:
        indice = json.load(f)
    vetorizador = None
    if indice.get("vetorizador"):
        vetorizador = joblib.load(os.path.join(DIR_DADOS, indice["vetorizador"]))
    return indice, vetorizador


class Repositorio:
    """Leitura com cache: so recarrega do disco quando o arquivo muda."""

    def __init__(self):
        self._trava = threading.Lock()
        self._mtime = None
        self.indice, self.vetorizador = dict(INDICE_VAZIO), None

    def atual(self):
        with self._trava:
            mtime = os.path.getmtime(ARQ_INDICE) if os.path.exists(ARQ_INDICE) else None
            if mtime != self._mtime:
                self.indice, self.vetorizador = carregar()
                self._mtime = mtime
            return self.indice, self.vetorizador
