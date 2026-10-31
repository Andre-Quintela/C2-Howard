"""
Circuit breaker (disjuntor) - adaptado do modelo de referencia do kit (Aula 11).

Estados:
  fechado -> deixa passar (normal); conta falhas consecutivas
  aberto  -> recusa na hora, sem tentar (dependencia esta quebrada)
  meio    -> passado o tempo de espera, deixa passar UMA chamada de teste;
             sucesso fecha o circuito, falha reabre

Mudancas em relacao ao kit:
  - thread-safe (o FastAPI executa rotas sincronas em um pool de threads);
  - no estado "meio" so UMA chamada de teste passa; as demais sao recusadas;
  - nome, contadores e um retrato do estado para expor em /saude.
"""
import logging
import threading
import time

log = logging.getLogger("disjuntor")


class CircuitoAberto(Exception):
    """Levantada quando o disjuntor esta aberto e recusa a chamada."""


class CircuitBreaker:

    def __init__(self, nome="dependencia", limite_falhas=5, espera_segundos=30):
        self.nome = nome
        self.limite_falhas = limite_falhas
        self.espera_segundos = espera_segundos
        self.falhas = 0
        self.estado = "fechado"
        self.aberto_em = 0.0
        self.recusadas = 0
        self._teste_em_andamento = False
        self._trava = threading.Lock()

    def chamar(self, funcao, *args, **kwargs):
        self._antes_da_chamada()
        try:
            resultado = funcao(*args, **kwargs)
        except Exception:
            self._registrar_falha()
            raise
        self._registrar_sucesso()
        return resultado

    def _antes_da_chamada(self):
        with self._trava:
            if self.estado == "aberto":
                if time.time() - self.aberto_em >= self.espera_segundos:
                    self._mudar_estado("meio")
                else:
                    self.recusadas += 1
                    raise CircuitoAberto(f"disjuntor '{self.nome}' aberto: chamada recusada")
            if self.estado == "meio":
                if self._teste_em_andamento:
                    self.recusadas += 1
                    raise CircuitoAberto(f"disjuntor '{self.nome}' meio-aberto: teste em andamento")
                self._teste_em_andamento = True

    def _registrar_falha(self):
        with self._trava:
            self.falhas += 1
            self._teste_em_andamento = False
            if self.falhas >= self.limite_falhas or self.estado == "meio":
                self._mudar_estado("aberto")
                self.aberto_em = time.time()

    def _registrar_sucesso(self):
        with self._trava:
            self.falhas = 0
            self._teste_em_andamento = False
            self._mudar_estado("fechado")

    def _mudar_estado(self, novo):
        if novo != self.estado:
            log.warning("disjuntor '%s': %s -> %s", self.nome, self.estado, novo)
            self.estado = novo

    def retrato(self):
        """Estado atual, para expor em /saude."""
        with self._trava:
            restante = 0.0
            if self.estado == "aberto":
                restante = max(0.0, self.espera_segundos - (time.time() - self.aberto_em))
            return {"estado": self.estado, "falhas": self.falhas,
                    "limite_falhas": self.limite_falhas,
                    "recusadas": self.recusadas,
                    "reabre_em_s": round(restante, 1)}
