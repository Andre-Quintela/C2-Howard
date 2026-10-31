"""
Avaliacao automatica simples da resposta (extensao opcional).

Nao e uma metrica de pesquisa - e um "termometro" barato, sem chamar outro LLM:

  fundamentacao = fracao dos termos de conteudo da RESPOSTA que aparecem
                  no contexto recuperado (resposta inventada -> valor baixo);
  cobertura     = fracao dos termos da PERGUNTA que aparecem no contexto
                  (o contexto fala do assunto perguntado?);
  citacoes      = referencias [n] citadas na resposta que existem no contexto.

aprovada = fundamentacao >= LIMIAR_FUNDAMENTACAO e cobertura >= LIMIAR_COBERTURA
"""
import re

from servicos.comum.texto import termos

LIMIAR_FUNDAMENTACAO = 0.6
LIMIAR_COBERTURA = 0.3

# linhas de moldura do modo simulado do kit, que nao sao conteudo da resposta
_MOLDURA_SIMULADA = re.compile(r"^\[MODO SIMULADO.*$|^Pergunta:.*$|Com base nos documentos recuperados:",
                               re.MULTILINE)


def avaliar(pergunta: str, resposta: str, contexto: list) -> dict:
    texto_contexto = " ".join(contexto)
    termos_contexto = termos(texto_contexto)
    termos_resposta = termos(_MOLDURA_SIMULADA.sub(" ", resposta))
    termos_pergunta = termos(pergunta)

    fundamentacao = (len(termos_resposta & termos_contexto) / len(termos_resposta)
                     if termos_resposta else 0.0)
    cobertura = (len(termos_pergunta & termos_contexto) / len(termos_pergunta)
                 if termos_pergunta else 0.0)
    refs_validas = {int(n) for n in re.findall(r"\[(\d+)\]", texto_contexto)}
    citacoes = sorted({int(n) for n in re.findall(r"\[(\d+)\]", resposta)} & refs_validas)

    return {"fundamentacao": round(fundamentacao, 3), "cobertura": round(cobertura, 3),
            "citacoes": citacoes,
            "aprovada": fundamentacao >= LIMIAR_FUNDAMENTACAO and cobertura >= LIMIAR_COBERTURA}
