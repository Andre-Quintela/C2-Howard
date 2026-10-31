"""
Servico 1 - INGESTAO: recebe documentos, gera embeddings e armazena.

Fluxo de escrita ASSINCRONO (mensageria):
  POST /documentos -> publica em stream:ingestao -> 202 Accepted
  worker-ingestao consome, vetoriza e persiste o indice em disco.

Leitura (REST, consumida pelo servico de recuperacao):
  GET  /indice      -> trechos + vetores (com versao, para cache)
  POST /vetorizar   -> vetoriza um texto com o MESMO vocabulario do indice

Rodar: uvicorn servicos.ingestao.app:app --port 8001
"""
import hashlib
import logging

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from servicos.comum import fila
from servicos.ingestao import armazenamento

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ingestao] %(name)s: %(message)s")

app = FastAPI(title="Ingestao - C2.A2")
repositorio = armazenamento.Repositorio()


class Documento(BaseModel):
    texto: str = Field(min_length=1)
    origem: str = "desconhecida"


class Texto(BaseModel):
    texto: str


def id_documento(doc: Documento) -> str:
    return hashlib.sha1(f"{doc.origem}\n{doc.texto}".encode("utf-8")).hexdigest()[:16]


@app.post("/documentos", status_code=202)
def receber_documentos(docs: list[Documento]):
    """Enfileira os documentos para indexacao e responde na hora."""
    try:
        cliente = fila.conectar()
        aceitos = []
        for d in docs:
            carga = {"id": id_documento(d), "origem": d.origem, "texto": d.texto}
            mensagem = fila.publicar(cliente, fila.STREAM_INGESTAO, carga)
            aceitos.append({"id": carga["id"], "origem": d.origem, "mensagem": mensagem})
    except redis.RedisError as erro:
        raise HTTPException(503, f"fila indisponivel, tente novamente: {erro}")
    return {"aceitos": len(aceitos), "documentos": aceitos,
            "status": "enfileirado - consulte GET /documentos/{id}"}


@app.post("/indexar", status_code=202)
def indexar(docs: list[Documento]):
    """Rota do kit, mantida por compatibilidade (agora tambem passa pela fila)."""
    return receber_documentos(docs)


@app.get("/documentos/{id_doc}")
def status_documento(id_doc: str):
    indice, _ = repositorio.atual()
    doc = indice["documentos"].get(id_doc)
    if doc is None:
        return {"id": id_doc, "indexado": False, "versao_indice": indice["versao"]}
    return {"id": id_doc, "indexado": True, **doc, "versao_indice": indice["versao"]}


@app.get("/indice")
def obter_indice(versao: int | None = None):
    """
    Consumido pelo servico de recuperacao. Se ele ja tem a versao atual
    (?versao=N), devolvemos so {"inalterado": true} e economizamos a rede.
    """
    indice, _ = repositorio.atual()
    if versao is not None and versao == indice["versao"]:
        return {"versao": indice["versao"], "inalterado": True}
    return {"versao": indice["versao"], "total": len(indice["trechos"]),
            "itens": [{"id": t["id"], "texto": t["texto"], "origem": t["origem"],
                       "vetor": t["vetor"]} for t in indice["trechos"]]}


@app.post("/vetorizar")
def vetorizar(t: Texto):
    indice, vetorizador = repositorio.atual()
    if vetorizador is None:
        raise HTTPException(503, "indice vazio: envie documentos para POST /documentos")
    return {"versao": indice["versao"], "vetor": vetorizador.vetorizar(t.texto)}


@app.get("/saude")
def saude():
    indice, _ = repositorio.atual()
    try:
        na_fila = fila.pendentes(fila.conectar(), fila.STREAM_INGESTAO, fila.GRUPO_INGESTAO)
        redis_ok = True
    except redis.RedisError:
        na_fila, redis_ok = None, False
    return {"status": "ok", "redis": redis_ok, "versao_indice": indice["versao"],
            "documentos": len(indice["documentos"]), "trechos": len(indice["trechos"]),
            "pendentes_na_fila": na_fila}
