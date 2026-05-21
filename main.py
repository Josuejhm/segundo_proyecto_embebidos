"""
main.py -- Orquestador principal AGRI-EDGE-IA

VERSIÓN MEJORADA:
- Entrada de voz integrada como ALTERNATIVA (no opción separada)
- En cada modalidad [1,2,3,L] se pregunta: ¿Escribir o grabar?
- Menú más limpio
"""

import logging
import sys


import yaml

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agri-edge-ia")

# ── Deteccion de intent por palabras clave ───────────────────────────────────

PALABRAS_DIAGNOSTICO = {
    "mancha", "manchas", "hoja", "hojas", "enfermedad", "hongo", "tizon",
    "amarilla", "amarillo", "negra", "negro", "lesion", "plaga", "sintoma",
    "planta", "follaje", "pudricion", "virus", "bacteria", "fusarium",
    "rhizoctonia", "infestans",
}

PALABRAS_RIEGO = {
    "agua", "riego", "regar", "humedad", "seco", "seca", "fertiliz",
    "abono", "nutriente", "nitrogeno", "potasio", "fosforo", "ph",
    "suelo", "lluvia", "irrigar", "fertilizacion",
}

PALABRAS_ECONOMIA = {
    "precio", "vender", "venta", "mercado", "pima", "costo", "ganancia",
    "dinero", "plata", "colones", "rentab", "margen", "kilo",
    "kilogramo", "negocio", "utilidad", "perdida",
}

PALABRAS_MANEJO = {
    "almacena", "almacenamiento", "almacenar", "semilla", "guardar",
    "bodega", "postcosecha", "conservar", "conservacion", "silo",
    "saco", "jaba", "brote", "brotacion",
}


def detectar_modo(texto: str) -> str:
    """Detecta el modo segun palabras clave."""
    palabras = set(
        texto.lower()
        .replace(",", " ").replace(".", " ").replace("?", " ")
        .split()
    )
    if palabras & PALABRAS_DIAGNOSTICO:
        return "diagnostico_fitosanitario"
    if palabras & PALABRAS_ECONOMIA:
        return "economia"
    if palabras & PALABRAS_RIEGO:
        return "riego_fertilizacion"
    if palabras & PALABRAS_MANEJO:
        return "riego_fertilizacion"
    return "diagnostico_fitosanitario"


def cargar_config() -> dict:
    with open("config/settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def aplicar_overrides_jetson(cfg: dict) -> dict:
    if cfg.get("entorno") == "jetson":
        overrides = cfg.get("jetson_overrides", {})
        cfg["ollama"].update(overrides)
        logger.info("Modo Jetson activado. Overrides: %s", overrides)
    return cfg


def mostrar_menu():
    print()
    print("-" * 52)
    print("  AGRI-EDGE-IA -- Asistente Agricola Offline")
    print("-" * 52)
    print("  [1] Diagnostico fitosanitario")
    print("  [2] Riego y fertilizacion")
    print("  [3] Analisis economico")
    print("  [L] Consulta libre")
    print("  [q] Salir")


def main():
    cfg = cargar_config()
    cfg = aplicar_overrides_jetson(cfg)

    nivel = cfg.get("logs", {}).get("level", "INFO")
    logging.getLogger().setLevel(getattr(logging, nivel, logging.INFO))

    from modules.llm_client import OllamaClient
    from modules.context_builder import build_context, validate_context, context_to_json
    from modules.prompt_builder import build_llm_request
    from modules.vision_mock import analyze as vision_analyze
    from modules.agri_logic import calcular_riego, analizar_economia
    from modules.persistence import AgriDatabase
    from modules.rag_retriever import RAGRetriever
    from modules import cli
    from modules.input_handler import solicitar_entrada, vocalizar_respuesta

    # ── Inicializar servicios ────────────────────────────────────────────────
    ollama_cfg = cfg["ollama"]
    cliente = OllamaClient(
        host=ollama_cfg["host"],
        model=ollama_cfg["model"],
        timeout=ollama_cfg["timeout"],
        num_predict=ollama_cfg["num_predict"],
        temperature=ollama_cfg["temperature"],
        stream=ollama_cfg.get("stream", True),
    )
    db = AgriDatabase(cfg["base_datos"]["path"])

    # RAG
    rag = None
    rag_cfg = cfg.get("rag", {})
    if rag_cfg.get("habilitado", False):
        rag = RAGRetriever(
            index_path=rag_cfg.get("index_path", "rag/index"),
            model_name=rag_cfg.get("model_name", "all-MiniLM-L6-v2"),
        )
        if rag.disponible:
            print("RAG activo -- contexto local disponible")
        else:
            print("AVISO: RAG no disponible. Ejecutar: python scripts/build_rag_index.py")
            rag = None

    # Verificar Ollama
    print(f"\nVerificando Ollama ({ollama_cfg['model']})...")
    if not cliente.health_check():
        print(
            f"ERROR: Modelo '{ollama_cfg['model']}' no disponible.\n"
            f"  Ejecuta: ollama pull {ollama_cfg['model']}\n"
            f"  Luego:   ollama serve"
        )
        sys.exit(1)
    print(f"Ollama OK -- {ollama_cfg['model']}")

    # ── Ciclo principal ──────────────────────────────────────────────────────
    while True:
        mostrar_menu()
        opcion = input("\nOpcion: ").strip().lower()

        if opcion == "q":
            print("\nHasta luego.")
            break

        # ── Determinar modo ──────────────────────────────────────────────────
        pregunta_libre = None

        if opcion == "1":
            modo = "diagnostico_fitosanitario"
            # Solicitar consulta (texto o voz)
            pregunta_libre = solicitar_entrada(
                "\n¿Cuál es tu consulta sobre el diagnóstico?",
                modo="texto_o_voz"
            )
            if not pregunta_libre:
                print("Consulta vacía, volviendo al menú.")
                continue
            modo = detectar_modo(pregunta_libre)
            print(f"  Modo detectado: {modo.replace('_', ' ')}")
            
        elif opcion == "2":
            modo = "riego_fertilizacion"
            # Solicitar consulta (texto o voz)
            pregunta_libre = solicitar_entrada(
                "\n¿Cuál es tu consulta sobre riego y fertilización?",
                modo="texto_o_voz"
            )
            if not pregunta_libre:
                print("Consulta vacía, volviendo al menú.")
                continue
            modo = detectar_modo(pregunta_libre)
            print(f"  Modo detectado: {modo.replace('_', ' ')}")
            
        elif opcion == "3":
            modo = "economia"
            # Solicitar consulta (texto o voz)
            pregunta_libre = solicitar_entrada(
                "\n¿Cuál es tu consulta sobre análisis económico?",
                modo="texto_o_voz"
            )
            if not pregunta_libre:
                print("Consulta vacía, volviendo al menú.")
                continue
            modo = detectar_modo(pregunta_libre)
            print(f"  Modo detectado: {modo.replace('_', ' ')}")
            
        elif opcion == "l":
            # Consulta libre (texto o voz)
            pregunta_libre = solicitar_entrada(
                "\n¿Cuál es tu consulta?",
                modo="texto_o_voz"
            )
            if not pregunta_libre:
                print("Consulta vacía, volviendo al menú.")
                continue
            modo = detectar_modo(pregunta_libre)
            print(f"  Modo detectado: {modo.replace('_', ' ')}")
        else:
            print("  Opcion invalida. Use 1, 2, 3, L o q.")
            continue

        # ── Etapa fenologica ─────────────────────────────────────────────────
        # En consulta libre, se usa vegetativo por defecto
        # En modos guiados, se solicita
        if opcion not in ("l",):
            etapas = ["emergencia", "vegetativo", "tuberizacion", "maduracion"]
            print(f"\nEtapas disponibles: {' | '.join(etapas)}")
            etapa_input = input("Etapa fenologica (Enter = vegetativo): ").strip().lower()
            etapa = etapa_input if etapa_input in etapas else "vegetativo"
        else:
            etapa = "vegetativo"

        # ── Datos segun modo ─────────────────────────────────────────────────
        suelo = {}
        costos = {}
        vision_result = None
        econ = {}
        riego = {}

        if opcion not in ("l",):
            if modo in ("diagnostico_fitosanitario", "riego_fertilizacion"):
                suelo = cli.solicitar_datos_suelo()

            if modo == "diagnostico_fitosanitario":
                print("\nEscenarios: default | sano | tizon_leve | tizon_grave | fusariosis | random")
                esc = input("Escenario de vision mock (Enter = default): ").strip() or "default"
                vision_result = vision_analyze(escenario=esc)
                print(
                    f"Vision: {vision_result['disease_detected']} "
                    f"(severidad {vision_result['severity_index']})"
                )

            if modo == "riego_fertilizacion" and suelo:
                try:
                    riego = calcular_riego(float(suelo.get("humedad_pct", 60)), etapa)
                    print(f"Riego calculado: {riego.get('frecuencia', 'N/A')}")
                except Exception as e:
                    logger.warning("Error calculando riego: %s", e)

            if modo == "economia":
                costos = cli.solicitar_datos_economia()
                try:
                    econ = analizar_economia(
                        costos["costo_total_crc"],
                        costos["rendimiento_esperado_kg"],
                        costos["calidad"],
                    )
                    costos.update(econ)
                except Exception as e:
                    logger.warning("Error en analisis economico: %s", e)

        # ── RAG ──────────────────────────────────────────────────────────────
        rag_fragmentos = []
        if rag:
            if pregunta_libre:
                rag_fragmentos = rag.retrieve(pregunta_libre, n=2)
            else:
                query_rag = ""
                if vision_result:
                    query_rag += f" {vision_result.get('disease_detected', '')}"
                rag_fragmentos = rag.retrieve_para_modo(modo, query_rag)
            if rag_fragmentos:
                fuentes = ", ".join(f["fuente"] for f in rag_fragmentos)
                print(f"RAG: {len(rag_fragmentos)} fragmento(s) -- {fuentes}")

        # ── Contexto JSON ────────────────────────────────────────────────────
        modo_prompt = "consulta_libre" if pregunta_libre else modo
        try:
            suelo_valido = suelo if suelo and any(v is not None for v in suelo.values()) else None
            ctx = build_context(
                modo=modo,
                etapa_fenologica=etapa,
                suelo=suelo_valido,
                vision_result=vision_result,
                costos=costos or None,
                rag_fragmentos=rag_fragmentos,
            )
            if pregunta_libre:
                ctx["pregunta"] = pregunta_libre
        except ValueError as e:
            print(f"ERROR en contexto: {e}")
            continue

        for advertencia in validate_context(ctx):
            print(f"AVISO: {advertencia}")

        print("\n--- CONTEXTO JSON ENVIADO AL LLM ---")
        print(context_to_json(ctx, indent=True))
        print("-------------------------------------\n")

        # ── LLM ──────────────────────────────────────────────────────────────
        prompt = build_llm_request(mode=modo_prompt, context=ctx)
        print("Consultando al LLM...")
        resultado = cliente.generate(prompt)

        db.log_llm(modo, resultado)

        if not resultado["success"]:
            print(f"ERROR LLM: {resultado['error']}")
            continue

        # ── Guardar en BD ────────────────────────────────────────────────────
        try:
            if modo == "diagnostico_fitosanitario" and vision_result:
                db.guardar_diagnostico(etapa, vision_result, suelo, resultado)
            elif modo == "riego_fertilizacion" and riego:
                db.guardar_riego(etapa, suelo, riego, resultado["response"])
            elif modo == "economia" and econ:
                db.guardar_economia(econ, resultado["response"])
        except Exception as e:
            logger.warning("Error guardando en BD: %s", e)

        # ── Resultado ────────────────────────────────────────────────────────
        cli.mostrar_resultado(resultado, modo)

        print(
            f"\n[Latencia: {resultado['latency_s']:.1f}s | "
            f"Tokens entrada: {resultado['prompt_tokens']} | "
            f"Tokens salida: {resultado['response_tokens']}]"
        )

        # ── VOCALIZAR SI SE DESEA ────────────────────────────────────────────
        if input("\n¿Vocalizar respuesta? [s/N]: ").strip().lower() == "s":
            json_data = resultado.get("json_data")
            vocalizar_respuesta(json_data)

        if input("\nOtra consulta? [s/N]: ").strip().lower() != "s":
            print("\nHasta luego.")
            break

    db.close()


if __name__ == "__main__":
    main()
