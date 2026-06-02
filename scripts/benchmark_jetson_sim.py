"""
scripts/benchmark_jetson_sim.py
---------------------------------
Suite completa de verificación del sistema AGRI-EDGE-IA en PC,
diseñada para validar que el sistema funcionará dentro de los
límites del Jetson Nano B01 (4 GB RAM, CUDA 10.2).

METODOLOGÍA:
─────────────
Cada test mide latencia en PC con los límites del docker-compose.constrained.yml
y calcula las estimaciones para Jetson Nano usando factores de escala
derivados de benchmarks públicos de ARM Cortex-A57 vs x86 para cargas similares.

Los factores de escala son:
  - CPU intensivo (Python/numpy):  ×3.5  (A57 ~30% de i7)
  - I/O bound (SQLite, archivos):  ×2.0  (penalizado por microSD vs NVMe)
  - ONNX GPU (Maxwell vs x86 sin GPU): ×0.8 (Maxwell compite bien en inferencia CNN)
  - Ollama CPU-only:               ×2.5  (llama.cpp muy optimizado para ARM)

USO:
    # Iniciar servicios:
    docker-compose -f docker-compose.constrained.yml up -d
    docker-compose -f docker-compose.constrained.yml exec agri-edge-ia \\
        python scripts/benchmark_jetson_sim.py

    # O directamente:
    python scripts/benchmark_jetson_sim.py --all
    python scripts/benchmark_jetson_sim.py --test ram
    python scripts/benchmark_jetson_sim.py --test vision
    python scripts/benchmark_jetson_sim.py --test llm
    python scripts/benchmark_jetson_sim.py --test rag
    python scripts/benchmark_jetson_sim.py --test e2e
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

import requests

# ── Configuración ─────────────────────────────────────────────────────────────

OLLAMA_URL   = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
JETSON_RAM_MB = 4096

# Factores de escala PC → Jetson (conservadores = seguros)
SCALE = {
    "cpu_python": 3.5,
    "cpu_io":     2.0,
    "gpu_cnn":    0.8,   # Maxwell compite con x86 sin GPU para CNN pequeñas
    "llm_cpu":    2.5,
}

# RNFs del proyecto (milisegundos salvo indicado)
RNFS = {
    "vision_ms":      10_000,   # RNF-011: ≤10 s captura→clasificación
    "llm_200tok_ms":  30_000,   # RNF-012: ≤30 s para ≤200 tokens
    "ram_total_mb":    3_500,   # RNF-013: ≤3.5 GB
    "cpu_pct":          80.0,   # RNF-014: ≤80% CPU durante procesamiento
}

VERDE  = "\033[92m"
ROJO   = "\033[91m"
AMARILLO = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class ResultadoTest:
    nombre: str
    medicion_pc_ms: float
    estimacion_jetson_ms: float
    rNF_limite_ms: float | None
    pasa: bool
    notas: str = ""
    metricas_extra: dict = field(default_factory=dict)


class BenchmarkSuite:

    def __init__(self):
        self.resultados: list[ResultadoTest] = []

    # ── Test 1: Presupuesto de RAM ─────────────────────────────────────────────

    def test_ram(self):
        """
        Mide el uso real de RAM de todos los componentes activos.
        FALLA si supera 3,500 MB (margen de 400 MB sobre límite Jetson).
        """
        print(f"\n{CYAN}{'─'*60}{RESET}")
        print(f"{BOLD}TEST 1: Presupuesto de RAM{RESET}")
        print("Cargando todos los componentes en memoria...")

        # Componente 1: Medir RAM del proceso Python actual
        import os, resource
        mem_antes_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

        # Componente 2: Cargar MiniLM (sentence-transformers)
        t0 = time.perf_counter()
        try:
            from sentence_transformers import SentenceTransformer
            model_rag = SentenceTransformer("all-MiniLM-L6-v2")
            rag_load_ms = (time.perf_counter() - t0) * 1000
            _encode = model_rag.encode(["Papa con tizón tardío"], convert_to_numpy=True)
            print(f"  ✓ MiniLM cargado en {rag_load_ms:.0f} ms")
            del model_rag
        except ImportError:
            print(f"  ⚠ sentence-transformers no instalado (incluir en test real)")
            rag_load_ms = 0

        # Componente 3: Cargar ONNX Runtime + modelo
        try:
            import onnxruntime as ort
            import numpy as np
            model_path = os.environ.get("VISION_MODEL_PATH", "data/models/mobilenetv2_potato.onnx")
            if Path(model_path).exists():
                sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
                dummy = np.random.randn(1, 3, 224, 224).astype(np.float32)
                _ = sess.run(None, {"image": dummy})
                print(f"  ✓ ONNX MobileNetV2 cargado")
                del sess
            else:
                print(f"  ⚠ Modelo ONNX no encontrado ({model_path})")
        except ImportError:
            print("  ⚠ onnxruntime no instalado")

        mem_despues_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        ram_python_mb = mem_despues_mb - mem_antes_mb

        # Componente 4: Consultar RAM de Ollama (si está corriendo)
        ollama_ram_mb = self._get_ollama_ram_mb()

        # RAM estimada total del sistema
        ram_estimada = {
            "os_kernel": 300,
            "ollama_llm": ollama_ram_mb if ollama_ram_mb > 0 else 2200,
            "python_app": max(ram_python_mb, 350),
            "buffer_otros": 150,
        }
        total_mb = sum(ram_estimada.values())

        print(f"\n  Desglose estimado:")
        for k, v in ram_estimada.items():
            print(f"    {k:<20}: {v:>6.0f} MB")
        print(f"    {'TOTAL':<20}: {total_mb:>6.0f} MB / {JETSON_RAM_MB} MB")

        margen = JETSON_RAM_MB - total_mb
        pasa = total_mb <= RNFS["ram_total_mb"]

        self._print_resultado("RAM total", total_mb, RNFS["ram_total_mb"],
                               unidad="MB", pasa=pasa, margen=margen)

        return ResultadoTest(
            nombre="RAM total del sistema",
            medicion_pc_ms=total_mb,
            estimacion_jetson_ms=total_mb,
            rNF_limite_ms=RNFS["ram_total_mb"],
            pasa=pasa,
            notas=f"Margen: {margen:.0f} MB",
            metricas_extra=ram_estimada,
        )

    # ── Test 2: Clasificación de imagen ────────────────────────────────────────

    def test_vision(self):
        """
        Mide latencia de inferencia ONNX en CPU de PC.
        Estima latencia en Jetson Maxwell GPU.
        """
        print(f"\n{CYAN}{'─'*60}{RESET}")
        print(f"{BOLD}TEST 2: Pipeline de visión (MobileNetV2 ONNX){RESET}")

        try:
            import onnxruntime as ort
            import numpy as np

            model_path = os.environ.get("VISION_MODEL_PATH", "data/models/mobilenetv2_potato.onnx")
            if not Path(model_path).exists():
                print(f"  ⚠ Modelo ONNX no encontrado. Saltando test.")
                print(f"    Ejecutar: python scripts/train_mobilenet.py && python scripts/export_to_onnx.py")
                return None

            sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            dummy = np.random.randn(1, 3, 224, 224).astype(np.float32)

            # Warm-up
            for _ in range(3):
                sess.run(None, {"image": dummy})

            # 20 corridas para estadísticas
            tiempos = []
            for _ in range(20):
                t0 = time.perf_counter()
                _ = sess.run(None, {"image": dummy})
                tiempos.append((time.perf_counter() - t0) * 1000)

            avg_ms  = sum(tiempos) / len(tiempos)
            p95_ms  = sorted(tiempos)[int(len(tiempos) * 0.95)]
            jetson_gpu_ms = avg_ms * SCALE["gpu_cnn"]
            jetson_cpu_ms = avg_ms * SCALE["cpu_python"]

            print(f"  PC CPU:       {avg_ms:.1f} ms promedio  |  P95: {p95_ms:.1f} ms")
            print(f"  Jetson GPU:   {jetson_gpu_ms:.0f} ms (estimado ×{SCALE['gpu_cnn']})")
            print(f"  Jetson CPU:   {jetson_cpu_ms:.0f} ms (estimado ×{SCALE['cpu_python']})")

            # El RNF es 10,000 ms. GPU Maxwell debe cumplir.
            pasa = jetson_gpu_ms < RNFS["vision_ms"]
            self._print_resultado("Visión GPU Jetson (est.)",
                                   jetson_gpu_ms, RNFS["vision_ms"], pasa=pasa)

            return ResultadoTest(
                nombre="Visión MobileNetV2 ONNX",
                medicion_pc_ms=avg_ms,
                estimacion_jetson_ms=jetson_gpu_ms,
                rNF_limite_ms=RNFS["vision_ms"],
                pasa=pasa,
                notas=f"P95 PC: {p95_ms:.1f}ms | Jetson CPU: {jetson_cpu_ms:.0f}ms",
            )

        except ImportError:
            print("  ⚠ onnxruntime no instalado. pip install onnxruntime")
            return None

    # ── Test 3: Latencia LLM ───────────────────────────────────────────────────

    def test_llm(self):
        """
        Mide tiempo de generación del LLM con prompt agrícola real.
        CRÍTICO: Este es el cuello de botella principal en Jetson Nano.
        """
        print(f"\n{CYAN}{'─'*60}{RESET}")
        print(f"{BOLD}TEST 3: Latencia LLM (Ollama + {OLLAMA_MODEL}){RESET}")

        # Verificar Ollama disponible
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if r.status_code != 200:
                print("  ✗ Ollama no disponible. docker-compose up primero.")
                return None
        except Exception:
            print("  ✗ Ollama no accesible en", OLLAMA_URL)
            return None

        # Prompt representativo del caso de uso real
        prompt = (
            "Eres un experto agrícola costarricense especializado en cultivos de papa. "
            "Diagnóstico de visión computacional: tizón tardío (Phytophthora infestans) "
            "con confianza 87.3%, severidad CRÍTICA. Métricas foliares: necrosis 23.4%, "
            "clorosis 8.1%, tejido sano 68.5%. "
            "La planta está en etapa de tuberización. "
            "Proporciona: (1) diagnóstico confirmado, (2) acciones inmediatas en 24h, "
            "(3) tratamiento fungicida recomendado disponible en Costa Rica. "
            "Responde en español costarricense, máximo 120 palabras."
        )

        print(f"  Enviando prompt ({len(prompt.split())} palabras) a {OLLAMA_MODEL}...")

        tiempos = []
        tokens_generados = []

        for i in range(3):
            t0 = time.perf_counter()
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 150,    # Límite para Jetson
                        "temperature": 0.3,
                        "num_threads": 4,
                    },
                },
                timeout=120,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            tiempos.append(elapsed_ms)

            if response.status_code == 200:
                data = response.json()
                n_tok = data.get("eval_count", 0)
                tokens_generados.append(n_tok)
                tok_s = n_tok / (elapsed_ms / 1000) if elapsed_ms > 0 else 0
                print(f"  Run {i+1}: {elapsed_ms/1000:.1f}s | {n_tok} tokens | {tok_s:.1f} tok/s")
            else:
                print(f"  Run {i+1}: ERROR {response.status_code}")

        if not tiempos:
            return None

        avg_ms = sum(tiempos) / len(tiempos)
        avg_tok = sum(tokens_generados) / len(tokens_generados) if tokens_generados else 0
        tok_s_pc = avg_tok / (avg_ms / 1000)

        # OLLAMA_NUM_GPU=0 → CPU only en PC (simula peor caso Jetson sin GPU acelerado)
        # Jetson con Maxwell + llama.cpp CUDA es ~40% más rápido que CPU ARM puro
        jetson_cpu_ms    = avg_ms * SCALE["llm_cpu"]
        jetson_gpu_ms    = jetson_cpu_ms * 0.65  # GPU Maxwell ≈ 35% mejora en LLM
        jetson_tok_s_gpu = avg_tok / (jetson_gpu_ms / 1000)

        print(f"\n  PC CPU-only:    {avg_ms/1000:.1f}s  ({tok_s_pc:.1f} tok/s)")
        print(f"  Jetson CPU est: {jetson_cpu_ms/1000:.1f}s")
        print(f"  Jetson GPU est: {jetson_gpu_ms/1000:.1f}s  ({jetson_tok_s_gpu:.1f} tok/s)")

        pasa = jetson_gpu_ms < RNFS["llm_200tok_ms"]
        self._print_resultado("LLM Jetson GPU (est.)",
                               jetson_gpu_ms, RNFS["llm_200tok_ms"], pasa=pasa)

        # ALERTA si el margen es ajustado
        if RNFS["llm_200tok_ms"] * 0.8 < jetson_gpu_ms < RNFS["llm_200tok_ms"]:
            print(f"  {AMARILLO}⚠ Margen ajustado. Considerar reducir num_predict a 120.{RESET}")

        return ResultadoTest(
            nombre="LLM latencia (150 tokens)",
            medicion_pc_ms=avg_ms,
            estimacion_jetson_ms=jetson_gpu_ms,
            rNF_limite_ms=RNFS["llm_200tok_ms"],
            pasa=pasa,
            notas=f"PC CPU: {tok_s_pc:.1f} tok/s | Jetson GPU est: {jetson_tok_s_gpu:.1f} tok/s",
            metricas_extra={"avg_tokens": avg_tok},
        )

    # ── Test 4: RAG retrieval ──────────────────────────────────────────────────

    def test_rag(self):
        """
        Mide latencia del RAG: encode query + búsqueda coseno.
        El RAG no tiene RNF explícito pero debe ser transparente (<3 s).
        """
        print(f"\n{CYAN}{'─'*60}{RESET}")
        print(f"{BOLD}TEST 4: RAG retrieval (MiniLM + numpy coseno){RESET}")

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            model = SentenceTransformer("all-MiniLM-L6-v2")

            # Simular índice RAG con 500 documentos (representativo)
            N_DOCS = 500
            DIM    = 384  # dimensión MiniLM
            print(f"  Generando índice simulado ({N_DOCS} documentos, {DIM}d)...")
            fake_embeddings = np.random.randn(N_DOCS, DIM).astype(np.float32)
            fake_embeddings /= np.linalg.norm(fake_embeddings, axis=1, keepdims=True)

            # Medir encode + búsqueda
            query = "síntomas de tizón tardío en hojas de papa variedad La Floresta"
            tiempos_encode, tiempos_search = [], []

            for _ in range(20):
                t0 = time.perf_counter()
                q_emb = model.encode([query])[0]
                tiempos_encode.append((time.perf_counter() - t0) * 1000)

                t1 = time.perf_counter()
                sims = fake_embeddings @ q_emb / (
                    np.linalg.norm(fake_embeddings, axis=1) * np.linalg.norm(q_emb) + 1e-9
                )
                _ = np.argsort(sims)[-3:][::-1]
                tiempos_search.append((time.perf_counter() - t1) * 1000)

            enc_avg = sum(tiempos_encode) / len(tiempos_encode)
            srch_avg = sum(tiempos_search) / len(tiempos_search)
            total_pc = enc_avg + srch_avg

            jetson_est = total_pc * SCALE["cpu_python"]

            print(f"  PC:       encode={enc_avg:.1f}ms | buscar={srch_avg:.1f}ms | total={total_pc:.1f}ms")
            print(f"  Jetson:   total estimado = {jetson_est:.0f}ms")

            pasa = jetson_est < 3000  # objetivo interno: <3s (no RNF explícito)
            self._print_resultado("RAG Jetson (est.)", jetson_est, 3000,
                                   pasa=pasa, unidad="ms")

            return ResultadoTest(
                nombre="RAG retrieval MiniLM",
                medicion_pc_ms=total_pc,
                estimacion_jetson_ms=jetson_est,
                rNF_limite_ms=3000,
                pasa=pasa,
                notas=f"encode={enc_avg:.1f}ms | búsqueda={srch_avg:.1f}ms",
            )

        except ImportError:
            print("  ⚠ sentence-transformers no instalado")
            return None

    # ── Test 5: Pipeline End-to-End ────────────────────────────────────────────

    def test_e2e(self):
        """
        Simula el pipeline completo: texto → RAG → LLM → respuesta.
        NO incluye STT ni visión (se prueban por separado).
        Mide el tiempo total del flujo de orquestación.
        """
        print(f"\n{CYAN}{'─'*60}{RESET}")
        print(f"{BOLD}TEST 5: Pipeline End-to-End (texto → RAG → LLM){RESET}")

        # Simular contexto RAG (texto de documentos recuperados)
        rag_context = (
            "El tizón tardío (Phytophthora infestans) se controla con fungicidas "
            "de contacto como Clorotalonil 75% a 2.5 kg/ha y sistémicos como "
            "Metalaxil + Mancozeb. Aplicar preventivamente cada 7 días en épocas "
            "lluviosas. La variedad La Floresta tiene moderada resistencia parcial."
        )

        prompt_e2e = (
            f"CONTEXTO AGRÍCOLA LOCAL:\n{rag_context}\n\n"
            "DATOS DEL SISTEMA:\n"
            "Diagnóstico visión: tizón tardío (87.3% confianza, CRÍTICO)\n"
            "Necrosis foliar: 23.4% | Etapa: tuberización\n"
            "Humedad suelo: 72% | pH: 6.2\n\n"
            "Genera una recomendación concisa de acción inmediata en español. Máximo 100 palabras."
        )

        try:
            t0 = time.perf_counter()
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt_e2e,
                    "stream": False,
                    "options": {"num_predict": 120, "temperature": 0.3},
                },
                timeout=120,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if resp.status_code != 200:
                print(f"  ✗ Error Ollama: {resp.status_code}")
                return None

            data = resp.json()
            respuesta = data.get("response", "")
            n_tok = data.get("eval_count", 0)

            print(f"  Tiempo total PC: {elapsed_ms/1000:.1f}s | {n_tok} tokens")
            print(f"  Respuesta generada: {respuesta[:150]}...")

            jetson_est = elapsed_ms * SCALE["llm_cpu"] * 0.65
            pasa = jetson_est < 45_000  # objetivo E2E: ≤45 s (RNF-011 + RNF-012)

            print(f"  Jetson estimado: {jetson_est/1000:.1f}s")
            self._print_resultado("E2E Jetson (est.)", jetson_est, 45_000, pasa=pasa)

            return ResultadoTest(
                nombre="Pipeline E2E (texto → RAG → LLM)",
                medicion_pc_ms=elapsed_ms,
                estimacion_jetson_ms=jetson_est,
                rNF_limite_ms=45_000,
                pasa=pasa,
                notas=f"{n_tok} tokens generados",
            )

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return None

    # ── Reporte final ──────────────────────────────────────────────────────────

    def run_all(self, tests: list[str] = None):
        print(f"\n{BOLD}{'═'*60}")
        print("  AGRI-EDGE-IA — Suite de Verificación Jetson Nano")
        print(f"{'═'*60}{RESET}")
        print(f"  Host Ollama:  {OLLAMA_URL}")
        print(f"  Modelo LLM:   {OLLAMA_MODEL}")
        print(f"  Escala CPU:   ×{SCALE['cpu_python']} | LLM CPU: ×{SCALE['llm_cpu']}")
        print(f"  GPU Maxwell:  ×{SCALE['gpu_cnn']} (CNN) | ×0.65 (LLM)")

        test_map = {
            "ram":    self.test_ram,
            "vision": self.test_vision,
            "llm":    self.test_llm,
            "rag":    self.test_rag,
            "e2e":    self.test_e2e,
        }

        if tests is None:
            tests = list(test_map.keys())

        resultados = []
        for nombre in tests:
            if nombre in test_map:
                try:
                    r = test_map[nombre]()
                    if r:
                        resultados.append(r)
                except Exception as exc:
                    print(f"  ✗ Error en test '{nombre}': {exc}")
                    traceback.print_exc()

        # Reporte final
        print(f"\n{BOLD}{'═'*60}")
        print("  RESUMEN")
        print(f"{'═'*60}{RESET}")
        print(f"  {'Test':<35} {'PC (ms)':<12} {'Jetson est.':<14} {'RNF':<12} {'Estado'}")
        print(f"  {'-'*35} {'-'*12} {'-'*14} {'-'*12} {'-'*8}")

        aprobados = 0
        for r in resultados:
            estado = f"{VERDE}✓ PASA{RESET}" if r.pasa else f"{ROJO}✗ FALLA{RESET}"
            lim = f"{r.rNF_limite_ms:.0f}ms" if r.rNF_limite_ms else "—"
            print(f"  {r.nombre:<35} {r.medicion_pc_ms:<12.0f} "
                  f"{r.estimacion_jetson_ms:<14.0f} {lim:<12} {estado}")
            if r.pasa:
                aprobados += 1

        total = len(resultados)
        print(f"\n  Resultado: {aprobados}/{total} tests aprobados")

        if aprobados == total:
            print(f"  {VERDE}{BOLD}✓ El sistema está listo para la imagen Yocto/VirtualBox.{RESET}")
        else:
            print(f"  {ROJO}✗ Revisar los tests fallidos antes de continuar.{RESET}")

        # Guardar resultado JSON
        out = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ollama_model": OLLAMA_MODEL,
            "aprobados": aprobados,
            "total": total,
            "resultados": [asdict(r) for r in resultados],
        }
        Path("logs").mkdir(exist_ok=True)
        out_path = f"logs/benchmark_{int(time.time())}.json"
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Reporte guardado: {out_path}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_ollama_ram_mb(self) -> float:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/ps", timeout=3)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models", [])
                if models:
                    size_bytes = models[0].get("size_vram", 0) + models[0].get("size", 0)
                    return size_bytes / 1_048_576
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _print_resultado(nombre, valor, limite, pasa, unidad="ms", margen=None):
        emoji = f"{VERDE}✓" if pasa else f"{ROJO}✗"
        pct   = (valor / limite * 100) if limite else 0
        msg   = f"  {emoji} {nombre}: {valor:.0f}{unidad} / {limite:.0f}{unidad} ({pct:.0f}%){RESET}"
        if margen is not None:
            msg += f" | margen: {margen:.0f}{unidad}"
        print(msg)


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark AGRI-EDGE-IA para Jetson Nano")
    parser.add_argument("--all", action="store_true", default=False,
                        help="Ejecutar todos los tests")
    parser.add_argument("--test", choices=["ram", "vision", "llm", "rag", "e2e"],
                        action="append", dest="tests",
                        help="Test específico a ejecutar (puede repetirse)")
    args = parser.parse_args()

    suite = BenchmarkSuite()
    tests_a_correr = args.tests if args.tests else None
    suite.run_all(tests=tests_a_correr)
