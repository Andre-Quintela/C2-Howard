# TAREFAS - Trabalho C2.A2 (RAG Distribuido)

## Nucleo obrigatorio

- [x] **1. Persistir o indice** - `servicos/ingestao/armazenamento.py`
      `dados/indice.json` + `dados/vetorizador-vN.joblib`, gravados com troca atomica.

- [x] **2. Busca por similaridade** - `servicos/recuperacao/app.py`
      Pergunta vetorizada via `POST /vetorizar` da ingestao, cosseno, top_k.

- [x] **3. Circuit breaker no LLM** - `servicos/geracao/pipeline.py`
      `com_retentativa(disjuntor.chamar(com_tempo_limite(gerar)))`; 503 com trechos quando aberto.

- [x] **4. Mensageria** - `servicos/comum/fila.py`, workers e `docker-compose.yml`
      Ingestao (`stream:ingestao`) e perguntas assincronas (`stream:perguntas`) por Redis Streams.

- [x] **5. Fluxo completo** - `scripts/demo_fluxo.py`

- [x] **6. README com diagrama** da arquitetura dos tres servicos.

## Extensoes opcionais

- [x] Reordenar os trechos por relevancia (reranking) - `servicos/recuperacao/rerank.py`
- [x] Citar quais documentos embasaram a resposta - campo `fontes`
- [x] Avaliacao automatica simples da qualidade da resposta - `servicos/geracao/avaliacao.py`
- [ ] Trocar TF-IDF por embeddings de verdade (sentence-transformers)

## Antes de entregar

- [x] Desligue a internet: o modo simulado do LLM mantem o sistema de pe?
- [x] Derrube o servico de recuperacao: o disjuntor abre como esperado?
- [x] A chave da API esta FORA do codigo (em variavel de ambiente)?
