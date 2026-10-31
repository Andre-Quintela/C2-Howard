# Servico de INGESTAO - build a partir da raiz do repositorio:
#   docker build -f servicos/ingestao/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# so o codigo comum + o proprio servico (cada servico e independente)
COPY servicos/__init__.py servicos/__init__.py
COPY servicos/comum servicos/comum
COPY servicos/ingestao servicos/ingestao

EXPOSE 8001
HEALTHCHECK --interval=5s --timeout=3s --retries=10   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/saude', timeout=2)"
CMD ["uvicorn", "servicos.ingestao.app:app", "--host", "0.0.0.0", "--port", "8001"]
