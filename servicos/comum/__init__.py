# Execucao local: carrega o .env da raiz (no Docker as variaveis vem do compose).
# Nao sobrescreve variaveis que ja existem no ambiente.
from dotenv import load_dotenv

load_dotenv()
