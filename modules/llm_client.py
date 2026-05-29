"""
modules/llm_client.py
---------------------
Cliente HTTP para la API REST de Ollama.

CAMBIOS EN ESTA VERSIÓN (adaptación Jetson 2 GB):

1. host por defecto cambiado a "http://localhost:11434":
   - En Jetson, Ollama corre directamente en el mismo dispositivo.
   - La variable de entorno OLLAMA_HOST sigue siendo el override.

2. Detección de OOM mejorada:
   - Cuando Ollama muere por falta de RAM, el kernel cierra el socket
     abruptamente. En Python eso se ve como ConnectionResetError, EOF,
     o BrokenPipeError, no como un error de HTTP.
   - Ahora se detectan esos casos y se muestra un mensaje orientativo
     específico para Jetson 2 GB.

3. stream=False como default en Jetson 2 GB:
   - El streaming divide la respuesta en muchos writes pequeños al buffer
     de Python. En RAM escasa eso puede causar fragmentación del heap.
   - Con stream=False la respuesta llega en un solo JSON compacto.
   - En PC de desarrollo se puede usar stream=True para ver los tokens.

4. _extraer_resumen() mejorado:
   - Extrae el texto DESPUÉS del JSON para pasarlo a Piper TTS.
   - Truncado a 200 chars para no hacer síntesis de voz interminable.
"""

import json
import logging
import os
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OllamaClient:

    def __init__(
        self,
        host:        str   = None,
        model:       str   = "agri-qwen3b",
        timeout:     int   = 90,
        num_predict: int   = 80,
        temperature: float = 0.1,
        stream:      bool  = False,
    ):
        if host is None:
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.host        = host.rstrip("/")
        self.model       = model
        self.timeout     = timeout
        self.num_predict = num_predict
        self.temperature = temperature
        self.stream      = stream
        self._endpoint   = f"{self.host}/api/generate"

    # ── Método principal ──────────────────────────────────────────────────────

    def generate(self, prompt: str) -> dict:
        """
        Envía el prompt al LLM y retorna un dict con:
          response        (str)        texto completo de respuesta
          json_data       (dict|None)  primer JSON válido extraído
          resumen         (str)        texto después del JSON (para TTS)
          latency_s       (float)      segundos totales
          prompt_tokens   (int)        tokens de entrada
          response_tokens (int)        tokens de salida
          success         (bool)
          error           (str|None)
        """
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": self.stream,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
            },
        }

        t0 = time.time()
        result = {
            "response":        "",
            "json_data":       None,
            "resumen":         "",
            "latency_s":       0.0,
            "prompt_tokens":   self._estimate_tokens(prompt),
            "response_tokens": 0,
            "success":         False,
            "error":           None,
        }

        try:
            if self.stream:
                result = self._generate_streaming(payload, result)
            else:
                result = self._generate_blocking(payload, result)

            if result["success"]:
                result["json_data"] = self._extraer_json(result["response"])
                result["resumen"]   = self._extraer_resumen(result["response"])

        except requests.exceptions.ConnectionError as e:
            result["error"] = (
                "No se pudo conectar a Ollama. "
                "¿Está corriendo? Ejecutar: ollama serve"
            )
            logger.error("ConnectionError: %s", e)

        except requests.exceptions.Timeout:
            result["error"] = (
                f"Timeout después de {self.timeout}s. "
                "En Jetson 2 GB verificar: "
                "(1) model='agri-qwen3b' con num_ctx=512, "
                "(2) num_predict=80, "
                "(3) entorno='jetson_2gb' en settings.yaml."
            )
            logger.error(result["error"])

        except Exception as e:
            msg = str(e).lower()
            # Síntomas de OOM en Jetson: el kernel OOM-killer termina el proceso
            # Ollama y el socket se cierra abruptamente.
            if any(k in msg for k in ("connection", "reset", "eof", "broken pipe", "remote end")):
                result["error"] = (
                    f"Posible OOM (Out Of Memory): {e}. "
                    "Acciones correctivas: "
                    "(1) Usar modelo 'agri-qwen3b' con num_ctx=512. "
                    "(2) Verificar con: python scripts/measure_ram.py. "
                    "(3) Reiniciar Ollama: systemctl restart ollama."
                )
            else:
                result["error"] = f"Error inesperado: {e}"
            logger.error(result["error"])

        finally:
            result["latency_s"] = round(time.time() - t0, 2)

        return result

    # ── Generación con streaming ──────────────────────────────────────────────

    def _generate_streaming(self, payload: dict, result: dict) -> dict:
        """
        Imprime cada token conforme llega desde Ollama.
        Útil en PC de desarrollo para ver que el modelo está respondiendo.
        NO recomendado en Jetson 2 GB (usar stream=False).
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
                    data  = json.loads(line)
                    token = data.get("response", "")
                    tokens.append(token)
                    print(token, end="", flush=True)
                    if data.get("done"):
                        result["response_tokens"] = data.get("eval_count", 0)
                        result["prompt_tokens"]   = data.get(
                            "prompt_eval_count", result["prompt_tokens"]
                        )
                        break
                except json.JSONDecodeError:
                    continue
        print()
        result["response"] = "".join(tokens)
        result["success"]  = bool(result["response"].strip())
        return result

    # ── Generación sin streaming (recomendado para Jetson 2 GB) ──────────────

    def _generate_blocking(self, payload: dict, result: dict) -> dict:
        """
        Espera la respuesta completa antes de retornar.
        Un solo JSON de respuesta = menos fragmentación de heap en RAM escasa.
        """
        r = requests.post(self._endpoint, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        result["response"]        = data.get("response", "")
        result["response_tokens"] = data.get("eval_count", 0)
        result["prompt_tokens"]   = data.get(
            "prompt_eval_count", result["prompt_tokens"]
        )
        result["success"] = bool(result["response"].strip())
        return result

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """
        Verifica que Ollama esté corriendo y el modelo esté disponible.
        Compara solo el nombre base (sin tag) para mayor flexibilidad.
        """
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            models      = [m["name"] for m in r.json().get("models", [])]
            nombre_base = self.model.split(":")[0]
            disponible  = any(nombre_base in m for m in models)
            if not disponible:
                logger.warning(
                    "Modelo '%s' no encontrado.\n"
                    "  Modelos instalados: %s\n"
                    "  Para crear agri-qwen3b:\n"
                    "    ollama pull qwen2.5:3b\n"
                    "    ollama create agri-qwen3b -f data/models/Modelfile.agri",
                    self.model, models,
                )
            return disponible
        except Exception as e:
            logger.error("Health check falló: %s", e)
            return False

    # ── Extracción de JSON ────────────────────────────────────────────────────

    @staticmethod
    def _extraer_json(texto: str) -> Optional[dict]:
        """
        Extrae el primer JSON válido de la respuesta del LLM.

        Maneja tres casos comunes en qwen2.5:3b:
          1. Markdown: ```json { ... } ```
          2. Texto explicativo antes del {
          3. Balanceo correcto de llaves anidadas
        """
        limpio = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()
        start  = limpio.find("{")
        if start < 0:
            return None

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

    # ── Extracción de resumen para TTS ────────────────────────────────────────

    @staticmethod
    def _extraer_resumen(texto: str, max_chars: int = 200) -> str:
        """
        Extrae el texto DESPUÉS del bloque JSON.
        Es el resumen en lenguaje simple que Piper TTS leerá en voz.
        Se trunca a max_chars para no hacer síntesis de voz interminable.
        """
        limpio   = re.sub(r"```(?:json)?[\s\S]*?```", "", texto).strip()
        end_json = limpio.rfind("}")
        if end_json >= 0 and end_json < len(limpio) - 1:
            resumen = limpio[end_json + 1:].strip()
            return resumen[:max_chars]
        if not limpio.startswith("{"):
            return limpio[:max_chars]
        return ""

    # ── Utilidad ──────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimación rápida: ~1 token por 4 caracteres."""
        return max(1, len(text) // 4)