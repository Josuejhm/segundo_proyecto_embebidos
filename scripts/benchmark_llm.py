"""
scripts/benchmark_llm.py
------------------------
Mide el rendimiento del LLM con prompts agrícolas representativos.

Métricas recolectadas:
  - Latencia total por consulta.
  - Tokens de entrada y salida.
  - Tasa de éxito de JSON válido.
  - Causa de fallo JSON (truncamiento vs texto extra).
  - Uso aproximado de RAM (via /proc/meminfo en Linux).

Uso:
  python scripts/benchmark_llm.py
  python scripts/benchmark_llm.py --runs 5 --model qwen2.5:3b
  python scripts/benchmark_llm.py --show-response   # imprime respuesta cruda
"""

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

# ── Instrucción de formato compartida ──────────────────────────────────────
# Decisiones de ingeniería de prompts para PHI-3-mini:
#   1. Instrucción en inglés: phi3 responde mejor a "Output ONLY" que a "Responde SOLO"
#   2. Esquema de campos mínimo: menos campos = menos tokens = menos truncamiento
#   3. Temperatura 0.1: minimiza variabilidad en respuesta de formato

_FMT = (
    "Output ONLY a valid JSON object. No markdown. No explanation. No extra text.\n"
    "Start your response immediately with { and end with }.\n"
)

NUM_PREDICT_BENCHMARK = 350  # subir de 200 a 350 para evitar truncamiento

CASOS_PRUEBA = [
    {
        "nombre": "diagnostico_tizon",
        "prompt": (
            _FMT
            + 'Context: {"crop":"papa","stage":"vegetativo",'
            '"vision":{"disease":"tizon_tardio","severity_index":0.75,"confidence":0.88}}\n'
            'JSON schema: {"diagnostico":"string","urgencia":"critico|alto|medio|bajo",'
            '"recomendacion":"string","dias_revision":integer}'
        ),
    },
    {
        "nombre": "riego_basico",
        "prompt": (
            _FMT
            + 'Context: {"crop":"papa","stage":"tuberizacion","soil":{"humidity_pct":35,"ph":6.0}}\n'
            'JSON schema: {"frecuencia":"string","volumen_litros":number,"urgencia":"alta|media|baja","advertencia":"string"}'
        ),
    },
    {
        "nombre": "economia_basica",
        "prompt": (
            _FMT
            + 'Context: {"costo_ciclo_crc":500000,"cosecha_kg":2800,"calidad":"segunda","precio_kg_crc":280}\n'
            'JSON schema: {"ingreso_crc":number,"margen_crc":number,"rentable":boolean,"decision":"vender|esperar|negociar"}'
    ),
},
]


def extraer_json(respuesta: str) -> tuple:
    """
    Extrae el primer JSON valido de la respuesta del LLM.
    Maneja markdown, texto previo y JSON truncado.
    Returns: (valido: bool, causa_fallo: str)
    """
    # Limpiar markdown ```json ... ```
    resp_limpia = re.sub(r"```(?:json)?\s*", "", respuesta).replace("```", "").strip()

    start = resp_limpia.find("{")
    if start < 0:
        return False, "sin_llaves"

    # Buscar cierre balanceado
    depth = 0
    end = -1
    for i, ch in enumerate(resp_limpia[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        return False, "truncado"

    try:
        json.loads(resp_limpia[start:end])
        return True, ""
    except json.JSONDecodeError as e:
        return False, "json_invalido"


def _ram_disponible_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for linea in f:
                if linea.startswith("MemAvailable"):
                    return round(int(linea.split()[1]) / 1024, 1)
    except Exception:
        pass
    return -1


def ejecutar_caso(host, model, timeout, prompt, show_response=False):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": NUM_PREDICT_BENCHMARK,
            "temperature": 0.1,
            "stop": ["\n\n"],
        },
    }
    t0 = time.time()
    try:
        r = requests.post(f"{host}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        respuesta = data.get("response", "")
        latency = round(time.time() - t0, 3)
        tokens_out = data.get("eval_count", 0)

        if show_response:
            print(f"    -- respuesta cruda ({tokens_out} tok): {repr(respuesta[:300])}")

        json_valido, causa_fallo = extraer_json(respuesta)
        truncado = tokens_out >= NUM_PREDICT_BENCHMARK - 5

        return {
            "latency_s": latency,
            "tokens_in": data.get("prompt_eval_count", 0),
            "tokens_out": tokens_out,
            "json_valido": json_valido,
            "causa_fallo": causa_fallo,
            "truncado": truncado,
            "success": True,
        }
    except Exception as e:
        return {
            "latency_s": round(time.time() - t0, 3),
            "success": False,
            "error": str(e),
            "json_valido": False,
            "causa_fallo": str(e),
            "truncado": False,
            "tokens_in": 0,
            "tokens_out": 0,
        }


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLM -- AGRI-EDGE-IA")
    parser.add_argument("--host", default="http://ollama:11434")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--show-response", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print(f"  AGRI-EDGE-IA -- Benchmark LLM")
    print(f"  Modelo: {args.model} | Runs: {args.runs} | num_predict: {NUM_PREDICT_BENCHMARK}")
    print("=" * 70)

    todos_resultados = []

    for caso in CASOS_PRUEBA:
        print(f"\n-- Caso: {caso['nombre']}")
        latencias = []
        json_ok = 0
        fallos = []

        for i in range(args.runs):
            ram = _ram_disponible_mb()
            res = ejecutar_caso(args.host, args.model, args.timeout,
                                caso["prompt"], args.show_response)
            latencias.append(res["latency_s"])
            if res["json_valido"]:
                json_ok += 1
            else:
                fallos.append(res["causa_fallo"])

            estado = "OK" if res["success"] else "ERR"
            json_str = "JSON-OK" if res["json_valido"] else f"JSON-FAIL({res['causa_fallo']})"
            trunc_str = " [TRUNCADO]" if res["truncado"] else ""
            print(f"  Run {i+1}: {estado} {res['latency_s']:.2f}s | "
                  f"in={res['tokens_in']} out={res['tokens_out']}{trunc_str} | "
                  f"{json_str} | RAM={ram}MB")

        p_json = round(json_ok / args.runs * 100)
        print(f"  -> Latencia: media={statistics.mean(latencias):.2f}s "
              f"min={min(latencias):.2f}s max={max(latencias):.2f}s")
        print(f"  -> Tasa JSON valido: {json_ok}/{args.runs} ({p_json}%)")
        if fallos:
            print(f"  -> Causas de fallo: {set(fallos)}")

        todos_resultados.append({
            "caso": caso["nombre"],
            "latencia_media": round(statistics.mean(latencias), 2),
            "tasa_json_pct": p_json,
        })

    print("\n" + "=" * 70)
    print("  RESUMEN EJECUTIVO")
    print("=" * 70)
    for r in todos_resultados:
        estado = "OK " if r["tasa_json_pct"] >= 80 else "REV"
        print(f"  [{estado}] {r['caso']:30s} {r['latencia_media']:.2f}s | JSON={r['tasa_json_pct']}%")

    lat_global = statistics.mean(r["latencia_media"] for r in todos_resultados)
    json_global = statistics.mean(r["tasa_json_pct"] for r in todos_resultados)

    print(f"\n  Latencia promedio global:  {lat_global:.2f}s  (criterio PC: <60s)")
    print(f"  Tasa JSON valido global:   {json_global:.0f}%  (criterio: >80%)")

    aprobado = lat_global < 60 and json_global >= 80
    print(f"\n  Estado Fase 1: {'APROBADO' if aprobado else 'REVISAR'}")

    if not aprobado and json_global < 80:
        print("\n  Diagnostico:")
        print("  - causa=truncado  -> NUM_PREDICT_BENCHMARK muy bajo, subirlo")
        print("  - causa=sin_llaves -> el modelo agrego texto antes del JSON")
        print("  - Ejecutar con --show-response para ver respuesta cruda")
        print("  - Probar temperatura 0.0 para mas determinismo")


if __name__ == "__main__":
    main()
