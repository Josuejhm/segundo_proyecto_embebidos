import json
import logging
import os          # ← agregado para leer variables de entorno
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OllamaClient:

    def __init__(
        self,
        host: str = None,          # ← ahora opcional
        model: str = "qwen2.5:3b",
        timeout: int = 60,
        num_predict: int = 300,
        temperature: float = 0.1,
        stream: bool = True,
    ):
        # Si no se pasa host, usar la variable de entorno o por defecto "http://ollama:11434"
        if host is None:
            host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_predict = num_predict
        self.temperature = temperature
        self.stream = stream
        self._endpoint = f"{self.host}/api/generate"

    # ── Método principal ─────────────────────────────────────────────────────

    def generate(self, prompt: str) -> dict:
        """
        Envía el prompt al LLM y retorna un dict con:
          response       (str)        texto completo de respuesta
          json_data      (dict|None)  primer JSON válido extraído
          resumen        (str)        texto después del JSON (para TTS)
          latency_s      (float)      segundos totales
          prompt_tokens  (int)        tokens de entrada estimados
          response_tokens(int)        tokens de salida reportados por Ollama
          success        (bool)
          error          (str|None)
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": self.stream,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
            },
        }

        t0 = time.time()
        result = {
            "response": "",
            "json_data": None,
            "resumen": "",
            "latency_s": 0.0,
            "prompt_tokens": self._estimate_tokens(prompt),
            "response_tokens": 0,
            "success": False,
            "error": None,
        }
        try:
            if self.stream:
                result = self._generate_streaming(payload, result)
            else:
                result = self._generate_blocking(payload, result)

            if result["success"]:
                result["json_data"] = self._extraer_json(result["response"])
                result["resumen"] = self._extraer_resumen(result["response"])

        except requests.exceptions.ConnectionError:
            result["error"] = (
                "No se pudo conectar a Ollama. "
                "¿Está corriendo? Ejecuta: ollama serve"
            )
            logger.error(result["error"])
        except requests.exceptions.Timeout:
            result["error"] = (
                f"Timeout después de {self.timeout}s. "
                "En Jetson aumentar timeout en settings.yaml."
            )
            logger.error(result["error"])
        except Exception as e:
            result["error"] = f"Error inesperado: {e}"
            logger.error(result["error"])
        finally:
            result["latency_s"] = round(time.time() - t0, 2)

        return result

    # ── Generación con streaming ─────────────────────────────────────────────
    def _generate_streaming(self, payload: dict, result: dict) -> dict:
        """
        Imprime cada token conforme llega desde Ollama.
        El agricultor ve que el sistema responde en 3-5s,
        no espera 20-30s en silencio.
        """
        tokens = []
        print("\n  [LLM] ", end="", flush=True)

        with requests.post(
            self._endpoint, json=payload, stream=True, timeout=self.timeout
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    tokens.append(token)
                    print(token, end="", flush=True)

                    if data.get("done"):
                        result["response_tokens"] = data.get("eval_count", 0)
                        result["prompt_tokens"] = data.get(
                            "prompt_eval_count", result["prompt_tokens"]
                        )
                        break
                except json.JSONDecodeError:
                    continue
        print()  # nueva línea al terminar
        result["response"] = "".join(tokens)
        result["success"] = bool(result["response"].strip())
        return result

    # ── Generación sin streaming ─────────────────────────────────────────────

    def _generate_blocking(self, payload: dict, result: dict) -> dict:
        """Espera la respuesta completa antes de retornar."""
        r = requests.post(self._endpoint, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        result["response"] = data.get("response", "")
        result["response_tokens"] = data.get("eval_count", 0)
        result["prompt_tokens"] = data.get(
            "prompt_eval_count", result["prompt_tokens"]
        )
        result["success"] = bool(result["response"].strip())
        return result

    # ── Health check ─────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Verifica que Ollama esté corriendo y el modelo disponible."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            # Comparar solo el nombre base (sin tag) para mayor flexibilidad
            nombre_base = self.model.split(":")[0]
            disponible = any(nombre_base in m for m in models)
            if not disponible:
                logger.warning(
                    "Modelo '%s' no encontrado.\n"
                    "Modelos instalados: %s\n"
                    "Ejecuta: ollama pull %s",
                    self.model, models, self.model,
                )
            return disponible
        except Exception as e:
            logger.error("Health check falló: %s", e)
            return False

    # ── Extracción de JSON ───────────────────────────────────────────────────

    @staticmethod
    def _extraer_json(texto: str) -> Optional[dict]:
        """
        Extrae el primer JSON válido de la respuesta.

        Maneja tres casos comunes en qwen2.5:3b:
          1. Markdown: ```json { ... } ```
          2. Texto explicativo antes del {
          3. Balanceo correcto de llaves anidadas
        """
        # Limpiar markdown
        limpio = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()

        start = limpio.find("{")
        if start < 0:
            return None

        # Buscar cierre balanceado (más robusto que rfind)
        depth, end = 0, -1
        for i, ch in enumerate(limpio[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end < 0:
            logger.warning("JSON truncado en respuesta del LLM.")
            return None

        try:
            return json.loads(limpio[start:end])
        except json.JSONDecodeError as e:
            logger.warning("JSON inválido en respuesta: %s", e)
            return None

    # ── Extracción de resumen para TTS ───────────────────────────────────────

    @staticmethod
    def _extraer_resumen(texto: str) -> str:
        """
        Extrae el texto después del bloque JSON.
        Es el resumen en lenguaje simple que Piper TTS leerá en voz.
        """
        # Quitar bloques markdown
        limpio = re.sub(r"```(?:json)?[\s\S]*?```", "", texto).strip()

        end_json = limpio.rfind("}")
        if end_json >= 0 and end_json < len(limpio) - 1:
            return limpio[end_json + 1:].strip()
        # Si no hay JSON, retornar el texto completo como resumen
        if not limpio.startswith("{"):
            return limpio
        return ""

    # ── Utilidad ─────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimación rápida: ~1 token por 4 caracteres."""
        return max(1, len(text) // 4)
