#!/usr/bin/env python3
"""
scripts/measure_ram.py
----------------------
Mide el consumo real de RAM de cada componente de AGRI-EDGE-IA.
Compara contra el presupuesto del Jetson Nano (4096 MB total).

Uso:
    python3 scripts/measure_ram.py
    python3 scripts/measure_ram.py --con-ollama   # incluye llamada real al LLM
"""

import argparse
import json
import os
import sys
import time

# ── Colores para terminal ────────────────────────────────────────────────────
OK    = "\033[92m✓\033[0m"
WARN  = "\033[93m⚠\033[0m"
ERR   = "\033[91m✗\033[0m"
BOLD  = "\033[1m"
RESET = "\033[0m"

# ── Presupuesto Jetson Nano B01 (de la propuesta de diseño) ─────────────────
PRESUPUESTO = {
    "SO Linux (Yocto, kernel, daemons)":    300,
    "PHI-3-mini / qwen Q4_K_M (modelo)":  2200,
    "OpenCV CUDA + pipeline visión":        400,
    "Ollama runtime":                       150,
    "Python + lógica agrícola":             200,
    "Qt6 + interfaz gráfica":              200,
    "Buffers imagen, audio, temporales":    150,
}
RAM_TOTAL_JETSON = 4096
RAM_RESERVA      = 400   # margen de seguridad


def medir_proceso_actual() -> float:
    """Mide RSS del proceso Python actual en MB."""
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def medir_componente(nombre: str, fn) -> tuple[float, any]:
    """Ejecuta fn() y devuelve (MB usados, resultado)."""
    antes = medir_proceso_actual()
    resultado = fn()
    despues = medir_proceso_actual()
    return max(despues - antes, 0.1), resultado


def medir_ram_ollama() -> dict:
    """Consulta la RAM que Ollama reporta vía /api/ps."""
    try:
        import requests
        r = requests.get("http://localhost:11434/api/ps", timeout=5)
        data = r.json()
        modelos = data.get("models", [])
        if modelos:
            size_vram = modelos[0].get("size_vram", 0) / 1024 / 1024
            size      = modelos[0].get("size", 0) / 1024 / 1024
            return {"modelo": modelos[0].get("name"), "ram_mb": size, "vram_mb": size_vram}
    except Exception:
        pass
    return {}


def ram_sistema_libre() -> dict:
    """Lee /proc/meminfo para obtener RAM total y libre."""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                info[k.strip()] = int(v.split()[0]) / 1024  # KB → MB
        return {
            "total_mb":     round(info.get("MemTotal", 0)),
            "libre_mb":     round(info.get("MemAvailable", 0)),
            "usada_mb":     round(info.get("MemTotal", 0) - info.get("MemAvailable", 0)),
            "buffers_mb":   round(info.get("Buffers", 0)),
            "cache_mb":     round(info.get("Cached", 0)),
        }
    except Exception:
        return {}


def barra(usado_mb: float, total_mb: float, ancho: int = 30) -> str:
    pct = min(usado_mb / total_mb, 1.0)
    lleno = int(pct * ancho)
    color = "\033[92m" if pct < 0.75 else "\033[93m" if pct < 0.90 else "\033[91m"
    return f"{color}{'█' * lleno}{'░' * (ancho - lleno)}\033[0m {pct*100:.1f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--con-ollama", action="store_true",
                        help="Incluir llamada real al LLM para medir RAM con modelo cargado")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*62}{RESET}")
    print(f"{BOLD}  AGRI-EDGE-IA — Medición de RAM{RESET}")
    print(f"{BOLD}{'='*62}{RESET}\n")

    resultados = {}

    # ── 1. RAM del sistema operativo ────────────────────────────────────────
    sys_ram = ram_sistema_libre()
    if sys_ram:
        print(f"{BOLD}Sistema operativo (PC actual):{RESET}")
        print(f"  RAM total   : {sys_ram['total_mb']:>6.0f} MB")
        print(f"  RAM usada   : {sys_ram['usada_mb']:>6.0f} MB")
        print(f"  RAM libre   : {sys_ram['libre_mb']:>6.0f} MB")
        print(f"  {barra(sys_ram['usada_mb'], sys_ram['total_mb'])}")
    print()

    # ── 2. RAG Retriever ────────────────────────────────────────────────────
    print(f"{BOLD}Midiendo componentes de la aplicación:{RESET}\n")

    base = medir_proceso_actual()

    sys.path.insert(0, ".")
    delta, rag = medir_componente(
        "RAG Retriever",
        lambda: __import__("modules.rag_retriever", fromlist=["RAGRetriever"]).RAGRetriever(
            index_path="rag/index"
        )
    )
    resultados["RAG (TF-IDF índice)"] = delta
    estado = OK if delta < 50 else WARN
    print(f"  {estado} RAG Retriever          : {delta:>6.1f} MB")

    # ── 3. numpy + sklearn (ya cargados por RAG) ────────────────────────────
    delta_np, _ = medir_componente(
        "numpy+sklearn",
        lambda: (__import__("numpy"), __import__("sklearn"))
    )
    resultados["numpy + sklearn"] = delta_np
    estado = OK if delta_np < 60 else WARN
    print(f"  {estado} numpy + sklearn        : {delta_np:>6.1f} MB")

    # ── 4. PyYAML ───────────────────────────────────────────────────────────
    delta_yaml, _ = medir_componente("yaml", lambda: __import__("yaml"))
    resultados["PyYAML"] = delta_yaml
    print(f"  {OK} PyYAML                : {delta_yaml:>6.1f} MB")

    # ── 5. prompt_builder ───────────────────────────────────────────────────
    delta_pb, _ = medir_componente(
        "prompt_builder",
        lambda: __import__("modules.prompt_builder", fromlist=["build_llm_request"])
    )
    resultados["prompt_builder"] = delta_pb
    print(f"  {OK} prompt_builder        : {delta_pb:>6.1f} MB")

    # ── 6. context_builder ──────────────────────────────────────────────────
    try:
        delta_cb, _ = medir_componente(
            "context_builder",
            lambda: __import__("modules.context_builder", fromlist=["build_context"])
        )
        resultados["context_builder"] = delta_cb
        print(f"  {OK} context_builder       : {delta_cb:>6.1f} MB")
    except Exception as e:
        print(f"  {WARN} context_builder       : no medido ({e})")

    # ── 7. agri_logic ───────────────────────────────────────────────────────
    try:
        delta_al, _ = medir_componente(
            "agri_logic",
            lambda: __import__("modules.agri_logic", fromlist=["calcular_riego"])
        )
        resultados["agri_logic"] = delta_al
        print(f"  {OK} agri_logic            : {delta_al:>6.1f} MB")
    except Exception as e:
        print(f"  {WARN} agri_logic            : no medido ({e})")

    # ── 8. persistence (sqlite3) ─────────────────────────────────────────────
    try:
        delta_db, _ = medir_componente(
            "persistence",
            lambda: __import__("modules.persistence", fromlist=["AgriDatabase"])
        )
        resultados["persistence (sqlite3)"] = delta_db
        print(f"  {OK} persistence (sqlite3) : {delta_db:>6.1f} MB")
    except Exception as e:
        print(f"  {WARN} persistence           : no medido ({e})")

    # ── 9. vision_mock ──────────────────────────────────────────────────────
    delta_vm, _ = medir_componente(
        "vision_mock",
        lambda: __import__("modules.vision_mock", fromlist=["analyze"])
    )
    resultados["vision_mock"] = delta_vm
    print(f"  {OK} vision_mock           : {delta_vm:>6.1f} MB")

    # ── 10. Ollama (RAM del proceso del servidor) ───────────────────────────
    print()
    print(f"{BOLD}Ollama (proceso externo):{RESET}")
    ollama_info = medir_ram_ollama()
    if ollama_info:
        ram_ollama = ollama_info.get("ram_mb", 0)
        print(f"  {OK} Modelo cargado        : {ollama_info['modelo']}")
        print(f"  {OK} RAM reportada         : {ram_ollama:>6.0f} MB")
        resultados["Ollama + modelo LLM"] = ram_ollama
    else:
        print(f"  {WARN} Ollama no reporta modelo cargado")
        print(f"       (modelo se carga en el primer request)")
        print(f"       Estimado de propuesta: ~2200 MB")
        resultados["Ollama + modelo LLM"] = 2200  # estimado

    # ── 11. Llamada real al LLM ─────────────────────────────────────────────
    if args.con_ollama:
        print()
        print(f"{BOLD}Prueba de llamada real al LLM:{RESET}")
        try:
            import requests
            t0 = time.time()
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2.5:3b", "prompt": "Hola", "stream": False,
                      "options": {"num_predict": 20}},
                timeout=60
            )
            t1 = time.time()
            data = r.json()
            tokens = data.get("eval_count", 0)
            tok_s  = tokens / max(data.get("eval_duration", 1) / 1e9, 0.001)
            print(f"  {OK} Latencia primera respuesta: {t1-t0:.1f}s")
            print(f"  {OK} Velocidad generación      : {tok_s:.1f} tok/s")
            print(f"  {'⚠ Lento para Jetson' if tok_s < 2 else OK+' Velocidad OK'}")

            # RAM después de llamada
            ollama_post = medir_ram_ollama()
            if ollama_post:
                print(f"  {OK} RAM Ollama post-llamada  : {ollama_post.get('ram_mb',0):.0f} MB")
        except Exception as e:
            print(f"  {ERR} Error en llamada: {e}")

    # ── Resumen total ────────────────────────────────────────────────────────
    total_app = sum(resultados.values())

    print()
    print(f"{BOLD}{'='*62}{RESET}")
    print(f"{BOLD}  RESUMEN — Comparación con presupuesto Jetson Nano{RESET}")
    print(f"{BOLD}{'='*62}{RESET}\n")

    print(f"  {'Componente':<35} {'Medido':>8}  {'Presupuesto':>11}")
    print(f"  {'─'*56}")

    for comp, presup in PRESUPUESTO.items():
        medido = resultados.get(comp, None)
        if medido is not None:
            estado = OK if medido <= presup else WARN
            print(f"  {estado} {comp:<33} {medido:>7.0f}MB  {presup:>8}MB")
        else:
            print(f"  {WARN} {comp:<33} {'---':>7}    {presup:>8}MB  (estimado)")

    print(f"  {'─'*56}")

    # Total estimado en Jetson
    total_estimado = sum(PRESUPUESTO.values())
    total_medido_app = total_app  # lo que medimos de la app Python

    print(f"\n  Total medido (Python app)  : {total_medido_app:>7.0f} MB")
    print(f"  Total presupuesto Jetson   : {total_estimado:>7} MB")
    print(f"  RAM total Jetson Nano B01  : {RAM_TOTAL_JETSON:>7} MB")
    print(f"  Margen de seguridad        : {RAM_RESERVA:>7} MB")
    print()

    # Veredicto
    if total_medido_app < 2500:
        print(f"  {OK} {BOLD}App Python cabe en Jetson{RESET}")
        print(f"     La app usa ~{total_medido_app:.0f} MB.")
        print(f"     El modelo LLM (~2200 MB) es el componente dominante.")
        print(f"     Total estimado en Jetson: ~{total_estimado} MB / {RAM_TOTAL_JETSON} MB")
        margen = RAM_TOTAL_JETSON - total_estimado
        color = "\033[92m" if margen >= RAM_RESERVA else "\033[93m"
        print(f"     Margen real: {color}{margen} MB\033[0m "
              f"({'✓ suficiente' if margen >= RAM_RESERVA else '⚠ ajustado'})")
    else:
        print(f"  {WARN} App Python usa {total_medido_app:.0f} MB — revisar dependencias")

    print(f"\n{BOLD}{'='*62}{RESET}\n")


if __name__ == "__main__":
    main()