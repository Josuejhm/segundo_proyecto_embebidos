"""
modules/llm_client.py
---------------------
Cliente HTTP para la API REST de Ollama.
Toda llamada al LLM debe pasar por este módulo, nunca directamente desde main.py.

Responsabilidades:
  - Enviar prompts al endpoint /api/generate de Ollama.
  - Controlar timeout y num_predict.
  - Medir latencia y tokens.
  - Detectar y reportar errores de conexión o respuesta.
  - NO construir prompts; eso lo hace prompt_builder.py.
"""

import json
import time
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class OllamaClient:
    """Cliente para la API REST de Ollama."""

    def __init__(self, host: str, model: str, timeout: int = 90, num_predict: int = 300,
                 temperature: float = 0.3):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_predict = num_predict
        self.temperature = temperature
        self._endpoint = f"{self.host}/api/generate"

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> dict:
        """
        Envía un prompt al LLM y retorna un dict con:
          - response (str): texto de respuesta
          - latency_s (float): tiempo total en segundos
          - prompt_tokens (int): tokens estimados de entrada
          - response_tokens (int): tokens de salida reportados por Ollama
          - success (bool)
          - error (str | None)
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
                "stop": ["</respuesta>"],
            },
        }

        t0 = time.time()
        result = {
            "response": "",
            "latency_s": 0.0,
            "prompt_tokens": self._estimate_tokens(prompt),
            "response_tokens": 0,
            "success": False,
            "error": None,
        }

        try:
            logger.debug("Enviando prompt a Ollama (%s)…", self.model)
            r = requests.post(self._endpoint, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            result["response"] = data.get("response", "")
            result["response_tokens"] = data.get("eval_count", 0)
            result["success"] = True
            logger.debug("Respuesta recibida — %d tokens.", result["response_tokens"])
        except requests.exceptions.ConnectionError:
            result["error"] = "No se pudo conectar a Ollama. ¿Está corriendo?"
            logger.error(result["error"])
        except requests.exceptions.Timeout:
            result["error"] = f"Timeout después de {self.timeout}s."
            logger.error(result["error"])
        except requests.exceptions.HTTPError as e:
            result["error"] = f"Error HTTP: {e}"
            logger.error(result["error"])
        except Exception as e:
            result["error"] = f"Error inesperado: {e}"
            logger.error(result["error"])
        finally:
            result["latency_s"] = round(time.time() - t0, 2)

        return result

    # ------------------------------------------------------------------
    # Salud del servicio
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Verifica que Ollama esté corriendo y el modelo esté disponible."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            available = any(self.model in m for m in models)
            if not available:
                logger.warning("Modelo '%s' no encontrado. Modelos disponibles: %s",
                               self.model, models)
            return available
        except Exception as e:
            logger.error("Health check falló: %s", e)
            return False

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimación rápida: ~1 token por 4 caracteres (heurística estándar)."""
        return max(1, len(text) // 4)
