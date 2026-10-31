"""
Worker de INGESTAO - consome a fila stream:ingestao (mensageria, TAREFA 4).

Para cada documento recebido:
  1. ignora se o id ja estiver no indice (idempotencia: a fila entrega
     "pelo menos uma vez", entao a mesma mensagem pode chegar duas vezes);
  2. quebra o texto em trechos;
  3. reajusta o vetorizador com TODOS os trechos (o vocabulario muda) e
     revetoriza o indice inteiro;
  4. grava no disco com versao nova e so entao confirma a mensagem (XACK).

Rodar: python -m servicos.ingestao.worker
"""
import logging

from servicos.comum import fila
from servicos.comum.embeddings import Vetorizador
from servicos.ingestao import armazenamento

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker-ingestao] %(name)s: %(message)s")
log = logging.getLogger("worker")


def indexar_documento(doc):
    indice, _ = armazenamento.carregar()
    if doc["id"] in indice["documentos"]:
        log.info("documento %s (%s) ja indexado; ignorando duplicata", doc["id"], doc["origem"])
        return

    trechos = indice["trechos"] + [
        {"id": f"{doc['id']}-{n}", "doc_id": doc["id"], "origem": doc["origem"], "texto": t}
        for n, t in enumerate(armazenamento.quebrar_em_trechos(doc["texto"]))
    ]

    vetorizador = Vetorizador()
    vetorizador.ajustar([t["texto"] for t in trechos])
    for t in trechos:
        t["vetor"] = vetorizador.vetorizar(t["texto"])

    novo = {
        "versao": indice["versao"] + 1,
        "documentos": {**indice["documentos"],
                       doc["id"]: {"origem": doc["origem"], "caracteres": len(doc["texto"])}},
        "trechos": trechos,
    }
    armazenamento.salvar(novo, vetorizador)
    log.info("indexado %s (%s): indice v%d com %d trechos",
             doc["id"], doc["origem"], novo["versao"], len(trechos))


if __name__ == "__main__":
    fila.consumir(fila.STREAM_INGESTAO, fila.GRUPO_INGESTAO, indexar_documento)
