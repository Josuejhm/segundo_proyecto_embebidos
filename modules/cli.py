"""
modules/cli.py
--------------
Módulo F6 — Interfaz de Usuario (Fase 0-1: CLI).

Provee un menú interactivo en terminal para el asistente AGRI-EDGE-IA.
Usa la librería `rich` para salida con formato visual mejorado.

Fase futura: este módulo se complementa con UI Qt6/PyQt6 y audio TTS/ASR.
"""

import json
import logging
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, FloatPrompt
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logger = logging.getLogger(__name__)
console = Console() if RICH_AVAILABLE else None


def imprimir(texto: str, estilo: str = "") -> None:
    if RICH_AVAILABLE:
        console.print(texto, style=estilo)
    else:
        print(texto)


def titulo(texto: str) -> None:
    if RICH_AVAILABLE:
        console.print(Panel(f"[bold green]{texto}[/bold green]", expand=False))
    else:
        print(f"\n=== {texto} ===")


def mostrar_resultado(resultado: dict, modo: str) -> None:
    """Muestra el resultado LLM formateado en consola."""
    titulo(f"Resultado — {modo.replace('_', ' ').title()}")
    respuesta = resultado.get("response", "Sin respuesta.")

    # Intentar parsear JSON embebido en la respuesta
    parsed = _extraer_json(respuesta)
    if parsed:
        if RICH_AVAILABLE:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Campo", style="cyan")
            table.add_column("Valor")
            for k, v in parsed.items():
                table.add_row(str(k), str(v))
            console.print(table)
        else:
            for k, v in parsed.items():
                print(f"  {k}: {v}")
    else:
        imprimir(respuesta)

    # Métricas
    imprimir(
        f"\n[dim]Latencia: {resultado.get('latency_s', 0):.1f}s | "
        f"Tokens entrada: {resultado.get('prompt_tokens', 0)} | "
        f"Tokens salida: {resultado.get('response_tokens', 0)}[/dim]"
        if RICH_AVAILABLE else
        f"\nLatencia: {resultado.get('latency_s', 0):.1f}s"
    )


def seleccionar_modo() -> str:
    """Muestra el menú principal y retorna el modo seleccionado."""
    opciones = {
        "1": "diagnostico_fitosanitario",
        "2": "riego_fertilizacion",
        "3": "economia",
        "q": "salir",
    }
    titulo("AGRI-EDGE-IA — Asistente Agrícola Offline")
    imprimir("Seleccione el modo de consulta:")
    imprimir("  [1] Diagnóstico fitosanitario")
    imprimir("  [2] Riego y fertilización")
    imprimir("  [3] Análisis económico")
    imprimir("  [q] Salir\n")

    while True:
        opcion = input("Opción: ").strip().lower()
        if opcion in opciones:
            return opciones[opcion]
        imprimir("Opción inválida.", "red")


def solicitar_datos_suelo() -> dict:
    """Solicita datos de suelo al usuario por teclado."""
    titulo("Datos del Suelo")
    try:
        humedad = float(input("Humedad del suelo (%) [0-100]: ") or "65")
        ph = float(input("pH del suelo [4.5-8.5]: ") or "6.0")
    except ValueError:
        humedad, ph = 65.0, 6.0
        imprimir("Valores inválidos, usando defaults: humedad=65%, pH=6.0", "yellow")

    nitrogeno = input("Nivel de Nitrógeno (alto/medio/bajo) [medio]: ").strip() or "medio"
    fosforo = input("Nivel de Fósforo (alto/medio/bajo) [bajo]: ").strip() or "bajo"
    potasio = input("Nivel de Potasio (alto/medio/bajo) [medio]: ").strip() or "medio"

    return {
        "humedad_pct": humedad,
        "ph": ph,
        "nitrogeno": nitrogeno,
        "fosforo": fosforo,
        "potasio": potasio,
    }


def solicitar_etapa() -> str:
    """Solicita la etapa fenológica al usuario."""
    etapas = ["emergencia", "vegetativo", "tuberizacion", "maduracion"]
    imprimir(f"Etapas disponibles: {', '.join(etapas)}")
    etapa = input("Etapa fenológica [vegetativo]: ").strip() or "vegetativo"
    if etapa not in etapas:
        imprimir(f"Etapa inválida, usando 'vegetativo'.", "yellow")
        etapa = "vegetativo"
    return etapa


def solicitar_datos_economia() -> dict:
    """Solicita datos económicos al usuario."""
    titulo("Análisis Económico")
    try:
        costo = float(input("Costo total del ciclo (₡): ") or "500000")
        rendimiento = float(input("Rendimiento esperado (kg): ") or "3000")
    except ValueError:
        costo, rendimiento = 500000.0, 3000.0
    calidad = input("Calidad del tubérculo (primera/segunda/tercera) [segunda]: ").strip() or "segunda"
    return {
        "costo_total_crc": costo,
        "rendimiento_esperado_kg": rendimiento,
        "calidad": calidad,
    }


def _extraer_json(texto: str) -> Optional[dict]:
    """
    Extrae el primer JSON valido de la respuesta del LLM.
    Maneja: markdown, texto previo al {, y llaves balanceadas.
    """
    import re
    limpio = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()
    start = limpio.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    for i, ch in enumerate(limpio[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        return json.loads(limpio[start:end])
    except Exception:
        return None