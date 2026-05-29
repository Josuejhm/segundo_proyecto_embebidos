#!/usr/bin/env python3
"""
scripts/measure_ram.py
----------------------
Monitor de RAM en tiempo real para Jetson Nano 2 GB.

PROPÓSITO:
  Verificar que el consumo de RAM no supera 1.9 GB durante la operación
  del sistema AGRI-EDGE-IA en Jetson Nano 2 GB.

USO:
  python3 scripts/measure_ram.py            # snapshot único
  python3 scripts/measure_ram.py --watch    # actualización cada 2s
  python3 scripts/measure_ram.py --watch --interval 5

PRESUPUESTO OBJETIVO (Jetson Nano 2 GB = 2048 MB):
  OS Yocto + daemons:            ~200 MB
  Python + numpy + sklearn:      ~180 MB
  Ollama runtime:                ~150 MB
  qwen2.5:3b Q3_K_M + KV-512:  ~1350 MB
  RAG + buffers app:              ~60 MB
  ──────────────────────────────────────
  Total sin TTS:                ~1940 MB  (94% del total)
  Piper TTS pico breve:          +80 MB   (durante síntesis)
"""

import argparse
import subprocess
import sys
import time

LIMITE_MB  = 1900   # 93% de 2048 MB → zona de peligro
OBJETIVO_MB = 1600  # 78% → zona segura

# ── Colores ANSI ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def leer_ram() -> dict:
    """Lee uso de RAM desde /proc/meminfo (Linux universal)."""
    try:
        with open("/proc/meminfo") as f:
            datos = {}
            for linea in f:
                partes = linea.split()
                if len(partes) >= 2:
                    datos[partes[0].rstrip(":")] = int(partes[1])

        total_kb     = datos.get("MemTotal", 0)
        disponible_kb = datos.get("MemAvailable", 0)
        usada_kb     = total_kb - disponible_kb

        return {
            "total_mb":       total_kb // 1024,
            "disponible_mb":  disponible_kb // 1024,
            "usada_mb":       usada_kb // 1024,
            "porcentaje_uso": round(usada_kb / total_kb * 100, 1) if total_kb else 0.0,
        }
    except FileNotFoundError:
        try:
            import psutil
            m = psutil.virtual_memory()
            return {
                "total_mb":      m.total // (1024*1024),
                "disponible_mb": m.available // (1024*1024),
                "usada_mb":      m.used // (1024*1024),
                "porcentaje_uso": round(m.percent, 1),
            }
        except ImportError:
            return {"total_mb": 0, "disponible_mb": 0, "usada_mb": 0, "porcentaje_uso": 0.0}


def leer_rss_ollama() -> int:
    """RSS del proceso Ollama en MB. Retorna 0 si no está corriendo."""
    try:
        result = subprocess.run(["pgrep", "-x", "ollama"],
                                capture_output=True, text=True, timeout=2)
        pids = result.stdout.strip().split()
        if not pids:
            return 0
        rss_kb = 0
        for pid in pids:
            try:
                with open(f"/proc/{pid}/status") as f:
                    for linea in f:
                        if linea.startswith("VmRSS:"):
                            rss_kb += int(linea.split()[1])
                            break
            except Exception:
                pass
        return rss_kb // 1024
    except Exception:
        return 0


def barra(usada: int, total: int, ancho: int = 28) -> str:
    if total == 0:
        return "[" + "?" * ancho + "]"
    lleno     = int(usada / total * ancho)
    limite_pos = int(LIMITE_MB / total * ancho) if total else ancho
    b = list("─" * ancho)
    for i in range(min(lleno, ancho)):
        b[i] = "█"
    if 0 <= limite_pos < ancho:
        b[limite_pos] = "|"
    return "[" + "".join(b) + "]"


def imprimir(ram: dict, ollama_mb: int):
    usada = ram["usada_mb"]
    total = ram["total_mb"]
    pct   = ram["porcentaje_uso"]

    col = GREEN if usada < OBJETIVO_MB else (YELLOW if usada < LIMITE_MB else RED)
    estado = (
        f"{GREEN}✓ SEGURO{RESET}"         if usada < OBJETIVO_MB else
        f"{YELLOW}⚠ PRECAUCIÓN{RESET}"    if usada < LIMITE_MB else
        f"{RED}{BOLD}✗ PELIGRO OOM{RESET}"
    )

    print(f"\n{BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║  AGRI-EDGE-IA — Monitor RAM          ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════╝{RESET}")
    print(f"  RAM Usada:    {col}{BOLD}{usada:>6} MB{RESET} / {total} MB")
    print(f"  Disponible:   {ram['disponible_mb']:>6} MB")
    print(f"  {col}{barra(usada, total)} {pct}%{RESET}")
    print(f"  Límite:       {LIMITE_MB} MB  |  Objetivo: {OBJETIVO_MB} MB")
    if ollama_mb > 0:
        print(f"  Ollama RSS:   {ollama_mb:>6} MB")
    print(f"  Estado:       {estado}")

    if usada >= LIMITE_MB:
        print(f"\n  {BOLD}Acciones correctivas:{RESET}")
        print("    1. Confirmar que el modelo es agri-qwen3b (num_ctx=512)")
        print("    2. Verificar num_predict=80 en settings.yaml")
        print("    3. sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches")
    print()


def main():
    parser = argparse.ArgumentParser(description="Monitor de RAM para AGRI-EDGE-IA")
    parser.add_argument("--watch", "-w", action="store_true", help="Modo continuo")
    parser.add_argument("--interval", "-i", type=float, default=2.0, help="Intervalo en segundos")
    args = parser.parse_args()

    if args.watch:
        print("Modo continuo — Ctrl+C para salir")
        try:
            while True:
                print("\033[2J\033[H", end="")
                imprimir(leer_ram(), leer_rss_ollama())
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitor detenido.")
            sys.exit(0)
    else:
        ram = leer_ram()
        imprimir(ram, leer_rss_ollama())
        sys.exit(1 if ram["usada_mb"] >= LIMITE_MB else 0)


if __name__ == "__main__":
    main()
