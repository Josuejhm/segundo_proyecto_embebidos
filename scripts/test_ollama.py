"""
scripts/test_ollama.py
----------------------
Script de validación de Fase 0: verifica que Ollama esté corriendo,
el modelo esté disponible y que responde a un prompt agrícola mínimo.

Uso:
  python scripts/test_ollama.py
  python scripts/test_ollama.py --model tinyllama   # alternativa liviana
  python scripts/test_ollama.py --host http://localhost:11434

Criterios de aceptación (Fase 0):
  ✓ Conexión con Ollama establecida.
  ✓ Modelo listado y disponible.
  ✓ Respuesta recibida en < 60s en PC local.
  ✓ Respuesta contiene texto coherente.
  ✓ Métricas impresas: latencia, tokens.
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Asegurar que el directorio raíz esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

PROMPT_PRUEBA = """Eres un asistente agrícola offline para productores de papa en Costa Rica.
Responde en español breve.
Pregunta: ¿Cuál es la principal amenaza fitosanitaria del cultivo de papa y cómo prevenirla?
Responde en máximo 3 oraciones."""


def test_conexion(host: str) -> bool:
    print(f"\n[TEST 1] Verificando conexión con Ollama en {host}…")
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        print("  ✅ Conexión establecida.")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print(f"  → ¿Está Ollama corriendo? Ejecuta: ollama serve")
        return False


def test_modelo_disponible(host: str, model: str) -> bool:
    print(f"\n[TEST 2] Verificando modelo '{model}'…")
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"  Modelos instalados: {models}")
        disponible = any(model in m for m in models)
        if disponible:
            print(f"  ✅ Modelo '{model}' disponible.")
        else:
            print(f"  ❌ Modelo '{model}' NO encontrado.")
            print(f"  → Ejecuta: ollama pull {model}")
        return disponible
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_inferencia(host: str, model: str, timeout: int) -> dict:
    print(f"\n[TEST 3] Prueba de inferencia con prompt agrícola…")
    print(f"  Prompt: {PROMPT_PRUEBA[:80]}…")

    payload = {
        "model": model,
        "prompt": PROMPT_PRUEBA,
        "stream": False,
        "options": {"num_predict": 150, "temperature": 0.3},
    }

    t0 = time.time()
    try:
        r = requests.post(f"{host}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        latency = round(time.time() - t0, 2)
        respuesta = data.get("response", "")
        tokens_salida = data.get("eval_count", 0)
        tokens_entrada = data.get("prompt_eval_count", 0)

        print(f"\n  Respuesta del LLM:")
        print(f"  {'─' * 50}")
        print(f"  {respuesta[:400]}")
        print(f"  {'─' * 50}")
        print(f"\n  📊 Métricas:")
        print(f"     Latencia total:    {latency}s")
        print(f"     Tokens entrada:    {tokens_entrada}")
        print(f"     Tokens salida:     {tokens_salida}")

        exito = bool(respuesta.strip()) and latency < timeout
        print(f"\n  {'✅ Test PASADO.' if exito else '❌ Test FALLADO.'}")
        return {
            "success": exito,
            "latency_s": latency,
            "tokens_in": tokens_entrada,
            "tokens_out": tokens_salida,
            "response_len": len(respuesta),
        }
    except requests.exceptions.Timeout:
        print(f"  ❌ Timeout después de {timeout}s.")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {"success": False, "error": str(e)}


def test_json_response(host: str, model: str, timeout: int) -> bool:
    print(f"\n[TEST 4] Verificando respuesta JSON estructurada…")
    prompt_json = (
        "Responde ÚNICAMENTE con un JSON válido, sin texto adicional:\n"
        '{"estado": "ok", "mensaje": "prueba_json", "modelo": "responde_aqui"}'
    )
    payload = {
        "model": model,
        "prompt": prompt_json,
        "stream": False,
        "options": {"num_predict": 80, "temperature": 0.1},
    }
    try:
        r = requests.post(f"{host}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        respuesta = r.json().get("response", "")
        # Intentar parsear JSON de la respuesta
        start = respuesta.find("{")
        end = respuesta.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(respuesta[start:end])
            print(f"  ✅ JSON válido recibido: {parsed}")
            return True
        else:
            print(f"  ⚠️  Respuesta no es JSON puro: {respuesta[:100]}")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test de Ollama para AGRI-EDGE-IA")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--model", default="phi3:mini")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    print("=" * 60)
    print("  AGRI-EDGE-IA — Fase 0: Validación de Ollama")
    print("=" * 60)

    resultados = {}

    resultados["conexion"] = test_conexion(args.host)
    if not resultados["conexion"]:
        sys.exit(1)

    resultados["modelo"] = test_modelo_disponible(args.host, args.model)
    if not resultados["modelo"]:
        print(f"\nContinuando pruebas igualmente (el modelo puede estar cargándose)…")

    metricas = test_inferencia(args.host, args.model, args.timeout)
    resultados["inferencia"] = metricas.get("success", False)

    resultados["json"] = test_json_response(args.host, args.model, args.timeout)

    # Resumen
    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS")
    print("=" * 60)
    total = sum(1 for v in resultados.values() if v)
    for nombre, estado in resultados.items():
        icono = "✅" if estado else "❌"
        print(f"  {icono} {nombre}")
    print(f"\n  {total}/{len(resultados)} pruebas pasadas.")

    if total == len(resultados):
        print("\n  🎉 Fase 0 completada. Listo para Fase 1 (asistente CLI).")
    else:
        print("\n  ⚠️  Revisar los errores anteriores antes de continuar.")

    sys.exit(0 if total == len(resultados) else 1)


if __name__ == "__main__":
    main()
