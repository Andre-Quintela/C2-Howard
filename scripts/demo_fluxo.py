"""
Demonstra o fluxo completo: pergunta entra, resposta fundamentada sai.

  python scripts/demo_fluxo.py [--url http://127.0.0.1:8003] ["sua pergunta"]

1) fluxo SINCRONO   - POST /perguntar
2) fluxo ASSINCRONO - POST /perguntas (fila) + GET /perguntas/{id}
"""
import argparse
import time

import requests

PERGUNTAS = [
    "O que diz o teorema CAP?",
    "Quais são os estados de um circuit breaker?",
    "Por que o processamento de mensagens deve ser idempotente?",
]


def mostrar(r):
    j = r.json()
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  erro: {j.get('erro') or j.get('detail')}")
        return
    print("  resposta:", j["resposta"].replace("\n", "\n            ")[:500])
    for f in j["fontes"]:
        print(f"  fonte [{f['ref']}] {f['origem']} (score {f['score']})")
    if j.get("avaliacao"):
        a = j["avaliacao"]
        print(f"  avaliacao: fundamentacao={a['fundamentacao']} cobertura={a['cobertura']} "
              f"citacoes={a['citacoes']} aprovada={a['aprovada']}")
    print(f"  recuperacao: {j['modo_recuperacao']} | {j['duracao_ms']} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8003")
    ap.add_argument("perguntas", nargs="*")
    args = ap.parse_args()
    perguntas = args.perguntas or PERGUNTAS

    print("=== 1) Fluxo SINCRONO: POST /perguntar ===")
    for p in perguntas:
        print(f"\n> {p}")
        mostrar(requests.post(f"{args.url}/perguntar", json={"pergunta": p}, timeout=60))

    print("\n=== 2) Fluxo ASSINCRONO: POST /perguntas -> fila -> worker-geracao ===")
    p = perguntas[-1]
    r = requests.post(f"{args.url}/perguntas", json={"pergunta": p}, timeout=10)
    j = r.json()
    print(f"\n> {p}\n  HTTP {r.status_code}: id={j['id']} status={j['status']}")
    for _ in range(120):
        time.sleep(0.5)
        registro = requests.get(f"{args.url}{j['consultar']}", timeout=5).json()
        print(f"  status: {registro['status']}")
        if registro["status"] in ("concluida", "falhou"):
            break
    if registro["status"] == "concluida":
        print(f"  processada por: {registro.get('worker')}")
        res = registro["resultado"]
        print("  resposta:", res["resposta"].replace("\n", "\n            ")[:300])
        print("  fontes:", ", ".join(f["origem"] for f in res["fontes"]))


if __name__ == "__main__":
    main()
