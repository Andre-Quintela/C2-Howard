"""
Registro das perguntas assincronas no Redis (chave pergunta:{id}, TTL 1h).

Ciclo de vida:  pendente -> concluida
                         -> aguardando_dependencia -> (nova tentativa pela fila)
                         -> falhou
"""
import json
import time

TTL_SEGUNDOS = 3600


def _chave(id_pergunta):
    return f"pergunta:{id_pergunta}"


def salvar(cliente, id_pergunta, registro):
    cliente.set(_chave(id_pergunta), json.dumps(registro, ensure_ascii=False), ex=TTL_SEGUNDOS)


def obter(cliente, id_pergunta):
    bruto = cliente.get(_chave(id_pergunta))
    return json.loads(bruto) if bruto else None


def atualizar(cliente, id_pergunta, **campos):
    registro = obter(cliente, id_pergunta) or {"id": id_pergunta}
    registro.update(campos, atualizada_em=time.time())
    salvar(cliente, id_pergunta, registro)
    return registro


def publicar_disjuntor(cliente, consumidor, retrato):
    """Workers publicam o estado do seu disjuntor para aparecer em /saude da API."""
    cliente.hset("disjuntores:workers", consumidor,
                 json.dumps({**retrato, "em": time.time()}))


def disjuntores_workers(cliente):
    return {k: json.loads(v) for k, v in cliente.hgetall("disjuntores:workers").items()}

