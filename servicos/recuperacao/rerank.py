"""
Reranking (extensao opcional): reordena os candidatos da busca vetorial.

O TF-IDF mede semelhanca de vocabulario no documento inteiro; aqui somamos
um sinal lexical simples - quantos termos da PERGUNTA aparecem no trecho
(sem acento, sem stopwords, singular/plural juntos).

  score = PESO_VETORIAL * cosseno + (1 - PESO_VETORIAL) * cobertura_da_pergunta
"""
from servicos.comum.texto import termos

PESO_VETORIAL = 0.7


def cobertura(pergunta: str, trecho: str) -> float:
    tp = termos(pergunta)
    if not tp:
        return 0.0
    return len(tp & termos(trecho)) / len(tp)


def reordenar(pergunta: str, candidatos: list, top_k: int, peso_vetorial=PESO_VETORIAL) -> list:
    """candidatos: dicts com 'texto' e 'score_vetorial'. Devolve top_k com 'score'."""
    resultado = []
    for c in candidatos:
        lexical = cobertura(pergunta, c["texto"])
        score = peso_vetorial * c.get("score_vetorial", 0.0) + (1 - peso_vetorial) * lexical
        resultado.append({**c, "score_lexical": round(lexical, 4), "score": round(score, 4)})
    resultado.sort(key=lambda c: c["score"], reverse=True)
    return [c for c in resultado if c["score"] > 0][:top_k]
