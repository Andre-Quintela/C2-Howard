"""Utilitarios de texto usados no reranking e na avaliacao da resposta."""
import re
import unicodedata

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas
para pra com sem sob sobre entre ate ao aos e ou mas que se nao sim ja mais menos muito
muita muitos muitas como quando onde qual quais quem cujo isso isto esse essa este esta
aquele aquela ele ela eles elas seu sua seus suas meu minha nosso nossa ser estar ter
haver foi sao era sera esta estao tem tinha pode podem deve devem diz dizer fazer faz
the of and or to is are what how why
""".split())


def normalizar(texto: str) -> str:
    """Minusculas e sem acentos: 'Partição' -> 'particao'."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def termos(texto: str) -> set:
    """Palavras de conteudo (sem stopwords, com 3+ letras), com radical simples."""
    palavras = re.findall(r"[a-z0-9]+", normalizar(texto))
    return {_radical(p) for p in palavras if len(p) >= 3 and p not in STOPWORDS}


def _radical(palavra: str) -> str:
    # radical bem simples: junta singular/plural ("particoes" ~ "particao")
    for sufixo in ("oes", "aes", "ais", "eis", "es", "s"):
        if len(palavra) > len(sufixo) + 3 and palavra.endswith(sufixo):
            return palavra[: -len(sufixo)]
    if len(palavra) > 5 and palavra.endswith("ao"):
        return palavra[:-2]
    return palavra
