from servicos.geracao.avaliacao import avaliar
from servicos.ingestao import armazenamento
from servicos.recuperacao.rerank import cobertura, reordenar


def test_cobertura_ignora_acento_stopwords_e_plural():
    assert cobertura("O que são partições?", "a particao de rede") == 1.0
    assert cobertura("qual a receita de bolo?", "teorema CAP") == 0.0


def test_reranking_promove_trecho_com_termos_da_pergunta():
    candidatos = [{"texto": "Raft elege um lider", "score_vetorial": 0.30},
                  {"texto": "O teorema CAP e as particoes", "score_vetorial": 0.25}]
    resultado = reordenar("o que diz o teorema CAP?", candidatos, top_k=2)
    assert resultado[0]["texto"].startswith("O teorema CAP")


def test_avaliacao_detecta_resposta_fundamentada_e_inventada():
    contexto = ["[1] (cap.txt) O teorema CAP trata de consistencia e disponibilidade"]
    boa = avaliar("o que e o teorema CAP?", "O teorema CAP trata de consistencia [1]", contexto)
    ruim = avaliar("o que e o teorema CAP?", "A Lua e feita de queijo", contexto)
    assert boa["aprovada"] and boa["citacoes"] == [1]
    assert not ruim["aprovada"] and ruim["fundamentacao"] == 0


def test_quebra_em_trechos():
    texto = "Primeiro paragrafo.\n\nSegundo. Com duas frases bem longas aqui."
    assert armazenamento.quebrar_em_trechos(texto, tamanho=20) == [
        "Primeiro paragrafo.", "Segundo.", "Com duas frases bem longas aqui."]


def test_worker_indexa_persiste_e_ignora_duplicata(tmp_path, monkeypatch):
    monkeypatch.setattr(armazenamento, "DIR_DADOS", str(tmp_path))
    monkeypatch.setattr(armazenamento, "ARQ_INDICE", str(tmp_path / "indice.json"))
    from servicos.ingestao import worker

    doc = {"id": "d1", "origem": "cap.txt", "texto": "O teorema CAP.\n\nParticoes acontecem."}
    worker.indexar_documento(doc)
    worker.indexar_documento(doc)  # entrega repetida pela fila

    indice, vetorizador = armazenamento.carregar()
    assert indice["versao"] == 1 and len(indice["trechos"]) == 2
    assert len(vetorizador.vetorizar("teorema")) == len(indice["trechos"][0]["vetor"])
