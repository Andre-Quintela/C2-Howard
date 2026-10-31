"""
Envia os arquivos .txt de documentos/ para a ingestao e espera a indexacao.

  python scripts/carregar_documentos.py [--pasta documentos] [--url http://127.0.0.1:8001]

A ingestao responde 202 na hora (os documentos vao para a fila); este script
acompanha GET /documentos/{id} ate o worker terminar de indexar.
"""
import argparse
import pathlib
import sys
import time

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="documentos")
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--espera", type=float, default=60, help="segundos para aguardar a indexacao")
    args = ap.parse_args()

    arquivos = sorted(pathlib.Path(args.pasta).glob("*.txt"))
    if not arquivos:
        sys.exit(f"nenhum .txt em {args.pasta}")
    docs = [{"texto": a.read_text(encoding="utf-8"), "origem": a.name} for a in arquivos]

    r = requests.post(f"{args.url}/documentos", json=docs, timeout=10)
    r.raise_for_status()
    aceitos = r.json()["documentos"]
    print(f"{len(aceitos)} documentos enfileirados (HTTP {r.status_code}):")
    for d in aceitos:
        print(f"  {d['origem']:<28} id={d['id']}  mensagem={d['mensagem']}")

    print("aguardando o worker indexar", end="", flush=True)
    faltando = {d["id"]: d["origem"] for d in aceitos}
    limite = time.time() + args.espera
    while faltando and time.time() < limite:
        for id_doc in list(faltando):
            if requests.get(f"{args.url}/documentos/{id_doc}", timeout=5).json()["indexado"]:
                faltando.pop(id_doc)
        print(".", end="", flush=True)
        time.sleep(0.5)
    print()

    saude = requests.get(f"{args.url}/saude", timeout=5).json()
    if faltando:
        sys.exit(f"ainda nao indexados: {list(faltando.values())} - veja os logs do worker-ingestao")
    print(f"pronto: indice v{saude['versao_indice']} com {saude['documentos']} documentos "
          f"e {saude['trechos']} trechos")


if __name__ == "__main__":
    main()
