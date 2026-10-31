"""
Demonstra o circuit breaker da chamada ao LLM, passo a passo.

  python scripts/demo_resiliencia.py [--url http://127.0.0.1:8003] [--modo erro|lento]

  1. liga o caos no LLM (erro = API fora do ar; lento = estoura o tempo-limite)
  2. faz perguntas: retentativas falham -> disjuntor ABRE -> 503 imediato
  3. desliga o caos e espera o tempo do disjuntor
  4. nova pergunta: estado MEIO-ABERTO, a chamada de teste passa -> FECHADO
"""
import argparse
import time

import requests

PERGUNTA = {"pergunta": "O que é consistência eventual?"}


def perguntar(url, n):
    t = time.time()
    r = requests.post(f"{url}/perguntar", json=PERGUNTA, timeout=120)
    j = r.json()
    estado = j["disjuntores"]["llm"]["estado"]
    detalhe = j.get("erro") or "resposta: " + j["resposta"].splitlines()[-1][:70]
    print(f"  #{n} HTTP {r.status_code} em {time.time() - t:5.2f}s | disjuntor={estado:<7} | {detalhe}")
    if r.status_code == 503 and j.get("fontes"):
        print(f"      degradacao: devolveu {len(j['fontes'])} trechos recuperados "
              f"({', '.join(f['origem'] for f in j['fontes'])})")
    return j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8003")
    ap.add_argument("--modo", default="erro", choices=["erro", "lento"])
    args = ap.parse_args()
    url = args.url

    print(f"Estado inicial do disjuntor: {requests.get(f'{url}/saude').json()['disjuntores']['llm']}")

    print(f"\n1) Ligando caos no LLM: modo '{args.modo}'")
    requests.post(f"{url}/admin/caos", json={"modo": args.modo}).raise_for_status()

    print("\n2) Perguntando com o LLM falhando (cada pergunta faz ate 3 tentativas):")
    for n in range(1, 5):
        perguntar(url, n)

    print("\n3) Desligando o caos (LLM 'volta ao ar')")
    requests.post(f"{url}/admin/caos", json={"modo": "nenhum"}).raise_for_status()
    llm = requests.get(f"{url}/saude").json()["disjuntores"]["llm"]
    print(f"   disjuntor ainda {llm['estado']}: recusa sem tentar por mais {llm['reabre_em_s']}s")
    perguntar(url, 5)
    espera = llm["reabre_em_s"] + 0.5
    print(f"   aguardando {espera:.1f}s ate o estado meio-aberto...")
    time.sleep(espera)

    print("\n4) Chamada de teste (meio-aberto) -> deve fechar o circuito:")
    perguntar(url, 6)
    print(f"\nEstado final: {requests.get(f'{url}/saude').json()['disjuntores']['llm']}")


if __name__ == "__main__":
    main()
