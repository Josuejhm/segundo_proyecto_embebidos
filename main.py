"""
main.py
-------
Orquestador principal de AGRI-EDGE-IA.

Flujo obligatorio:
  1. Leer configuración.
  2. Verificar Ollama disponible.
  3. Solicitar datos al usuario (CLI).
  4. Construir contexto JSON  →  context_builder.py
  5. Construir prompt final   →  prompt_builder.py
  6. Enviar al LLM            →  llm_client.py
  7. Mostrar resultado        →  cli.py
  8. Guardar en SQLite        →  persistence.py

REGLA: Nunca llamar directamente a OllamaClient con texto libre.
       Todo prompt debe pasar por build_llm_request().
"""
#curl -fsSL https://ollama.ai/install.sh | sh

import json
import logging
import sys
from pathlib import Path

import yaml

# ------------------------------------------------------------------
# Configuración de logging
# ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agri-edge-ia")


def cargar_config(ruta: str = "config/settings.yaml") -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    # ------------------------------------------------------------------
    # 1. Configuración
    # ------------------------------------------------------------------
    cfg = cargar_config()

    # Ajustar nivel de log
    nivel = cfg.get("logs", {}).get("level", "INFO")
    logging.getLogger().setLevel(getattr(logging, nivel, logging.INFO))

    # ------------------------------------------------------------------
    # 2. Imports de módulos (después de configuración)
    # ------------------------------------------------------------------
    from modules.llm_client import OllamaClient
    from modules.context_builder import build_context, validate_context, context_to_json
    from modules.prompt_builder import build_llm_request
    from modules.vision_mock import analyze as vision_analyze
    from modules.agri_logic import calcular_riego, recomendar_fertilizacion, analizar_economia
    from modules.persistence import AgriDatabase
    from modules import cli

    # ------------------------------------------------------------------
    # 3. Inicializar servicios
    # ------------------------------------------------------------------
    ollama_cfg = cfg["ollama"]
    cliente = OllamaClient(
        host=ollama_cfg["host"],
        model=ollama_cfg["model"],
        timeout=ollama_cfg["timeout"],
        num_predict=ollama_cfg["num_predict"],
        temperature=ollama_cfg["temperature"],
    )
    db = AgriDatabase(cfg["base_datos"]["path"])

    # Verificar salud de Ollama
    cli.imprimir("\n🔍 Verificando conexión con Ollama…", "cyan")
    if not cliente.health_check():
        cli.imprimir(
            f"❌ Ollama no disponible o modelo '{ollama_cfg['model']}' no cargado.\n"
            f"   Ejecuta: ollama pull {ollama_cfg['model']}\n"
            f"   Luego:   ollama serve",
            "red",
        )
        sys.exit(1)
    cli.imprimir(f"✅ Ollama OK — modelo: {ollama_cfg['model']}", "green")

    # ------------------------------------------------------------------
    # 4. Ciclo principal de consultas
    # ------------------------------------------------------------------
    while True:
        modo = cli.seleccionar_modo()
        if modo == "salir":
            cli.imprimir("\nHasta luego. 🌱", "green")
            break

        etapa = cli.solicitar_etapa()
        suelo = cli.solicitar_datos_suelo() if modo in (
            "diagnostico_fitosanitario", "riego_fertilizacion"
        ) else {}
        costos = cli.solicitar_datos_economia() if modo == "economia" else {}

        # --- F2: Visión (mock en Fase 0-1) ---
        vision_result = None
        if modo == "diagnostico_fitosanitario":
            escenario = input(
                "\nEscenario de visión mock [default/sano/tizon_leve/tizon_grave/fusariosis/random]: "
            ).strip() or "default"
            vision_result = vision_analyze(escenario=escenario)
            cli.imprimir(f"\n📷 Resultado visión mock: {vision_result['disease_detected']} "
                         f"(severidad {vision_result['severity_index']})", "yellow")

        # --- F4: Lógica agrícola ---
        if modo == "riego_fertilizacion" and suelo:
            riego = calcular_riego(suelo["humedad_pct"], etapa)
            fertil = recomendar_fertilizacion(
                etapa, suelo["nitrogeno"], suelo["fosforo"], suelo["potasio"]
            )
            cli.imprimir(f"\n💧 Riego calculado: {riego['frecuencia']} — "
                         f"{riego['volumen_litros_por_planta']} L/planta", "cyan")

        if modo == "economia" and costos:
            econ = analizar_economia(
                costos["costo_total_crc"], costos["rendimiento_esperado_kg"], costos["calidad"]
            )
            costos.update(econ)

        # --- F3: Construcción de contexto y prompt ---
        try:
            ctx = build_context(
                modo=modo,
                etapa_fenologica=etapa,
                suelo=suelo or None,
                vision_result=vision_result,
                costos=costos or None,
            )
        except ValueError as e:
            cli.imprimir(f"❌ Error en contexto: {e}", "red")
            continue

        advertencias = validate_context(ctx)
        for w in advertencias:
            cli.imprimir(f"⚠️  {w}", "yellow")

        # Mostrar contexto JSON antes de enviarlo (debug)
        print("\n--- CONTEXTO JSON ENVIADO AL LLM ---")
        print(context_to_json(ctx, indent=True))
        print("------------------------------------\n")

        prompt = build_llm_request(mode=modo, context=ctx)

        # --- Envío al LLM ---
        cli.imprimir("⏳ Consultando al LLM…", "cyan")
        resultado = cliente.generate(prompt)

        # Log en BD
        db.log_llm(modo, resultado)

        if not resultado["success"]:
            cli.imprimir(f"❌ Error LLM: {resultado['error']}", "red")
            continue

        # --- Guardar en SQLite ---
        if modo == "diagnostico_fitosanitario" and vision_result:
            db.guardar_diagnostico(etapa, vision_result, suelo, resultado)
        elif modo == "riego_fertilizacion":
            db.guardar_riego(etapa, suelo, riego, resultado["response"])
        elif modo == "economia":
            db.guardar_economia(econ, resultado["response"])

        # --- F6: Mostrar resultado ---
        cli.mostrar_resultado(resultado, modo)

        continuar = input("\n¿Realizar otra consulta? [s/N]: ").strip().lower()
        if continuar != "s":
            cli.imprimir("\nHasta luego. 🌱", "green")
            break

    db.close()


if __name__ == "__main__":
    main()
