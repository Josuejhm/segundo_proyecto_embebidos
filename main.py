"""
main.py — Orquestador principal AGRI-EDGE-IA
============================================

CAMBIOS RESPECTO A VERSIÓN ANTERIOR (adaptación Jetson 2 GB):

1. VISIÓN ELIMINADA:
   - Se removió toda importación y lógica de vision_classifier.py y vision_mock.py.
   - Razón: OpenCV CUDA + modelo ONNX consumen ~400 MB RAM. Con qwen2.5:3b Q3_K_M
     (~1350 MB) más el OS (~200 MB) más Python (~180 MB), no hay margen para la
     visión en un sistema de 2 GB.
   - Impacto en diagnóstico: el agricultor describe los síntomas por texto.
     El LLM razona sobre esa descripción + contexto RAG de enfermedades locales.
     El profesor fue consultado y aprobó esta simplificación.

2. STT ELIMINADO:
   - Se removió Whisper.cpp / solicitar_por_voz().
   - Razón: no se dispone de micrófono en el hardware actual.
   - La entrada es siempre por teclado o pantalla táctil.

3. TTS CONSERVADO:
   - Piper TTS sigue activo como proceso CLI (subprocess.run).
   - Se invoca DESPUÉS de liberar el contexto del LLM con gc.collect().
   - El proceso Piper vive ~10 segundos mientras habla y luego termina.

4. gc.collect() ESTRATÉGICO:
   - Después de construir el contexto y antes de llamar al LLM.
   - Después de recibir la respuesta del LLM y antes de Piper.
   - Libera buffers de Python que de otro modo quedan en heap.

5. OVERRIDE jetson_2gb:
   - aplicar_overrides_jetson() ahora reconoce entorno="jetson_2gb".
   - Aplica model="agri-qwen3b", num_predict=80, stream=false.
   - Fuerza rag.n_resultados=1.
"""

import gc
import logging
import sys

import yaml


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agri-edge-ia")

# ── Detección de modo por palabras clave ─────────────────────────────────────

PALABRAS_DIAGNOSTICO = {
    "mancha", "manchas", "hoja", "hojas", "enfermedad", "hongo", "tizon",
    "amarilla", "amarillo", "negra", "negro", "lesion", "plaga", "sintoma",
    "planta", "follaje", "pudricion", "virus", "bacteria", "fusarium",
    "rhizoctonia", "infestans", "marchitez", "necrosis", "clorosis",
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
    "bodega", "postcosecha", "conservar", "silo", "saco", "jaba",
    "brote", "brotacion",
}


def detectar_modo(texto: str) -> str:
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
        return "consulta_libre"
    return "consulta_libre"


def cargar_config() -> dict:
    """Carga config/settings.yaml."""
    with open("config/settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def aplicar_overrides_jetson(cfg: dict) -> dict:
    """
    Aplica overrides según el entorno configurado.
    jetson_2gb → usa jetson_2gb_overrides y fuerza rag.n_resultados=1.
    jetson     → usa jetson_overrides estándar.
    local      → sin cambios.
    """
    entorno = cfg.get("entorno", "local")
    if entorno == "jetson_2gb":
        overrides = cfg.get("jetson_2gb_overrides", {})
        cfg["ollama"].update(overrides)
        # Forzar n_resultados=1: crítico para no presionar el KV-cache en 2 GB
        cfg.setdefault("rag", {})["n_resultados"] = 1
        logger.info("Modo Jetson 2 GB. Overrides aplicados: %s", overrides)
    elif entorno == "jetson":
        overrides = cfg.get("jetson_overrides", {})
        cfg["ollama"].update(overrides)
        logger.info("Modo Jetson 4 GB. Overrides aplicados: %s", overrides)
    else:
        logger.info("Modo local (desarrollo). Sin overrides.")
    return cfg


def mostrar_menu():
    print()
    print("-" * 54)
    print("  AGRI-EDGE-IA — Asistente Agricola Offline")
    print("  (Sin vision — entrada por texto)")
    print("-" * 54)
    print("  [1] Diagnostico fitosanitario (descripcion de sintomas)")
    print("  [2] Riego y fertilizacion")
    print("  [3] Analisis economico")
    print("  [L] Consulta libre")
    print("  [q] Salir")


def solicitar_texto(mensaje: str) -> str:
    """
    Solicita texto al agricultor por teclado.
    STT eliminado: entrada solo por teclado o pantalla táctil.
    Retorna string vacío si el usuario no ingresa nada.
    """
    print(mensaje)
    return input("  → ").strip()


def main():
    cfg = cargar_config()
    cfg = aplicar_overrides_jetson(cfg)

    # Configurar nivel de logging
    nivel = cfg.get("logs", {}).get("level", "INFO")
    logging.getLogger().setLevel(getattr(logging, nivel, logging.INFO))

    # ── Importaciones tardías (evitar carga en RAM si no se usan) ────────────
    from modules.llm_client    import OllamaClient
    from modules.context_builder import build_context, validate_context, context_to_json
    from modules.prompt_builder  import build_llm_request
    from modules.agri_logic      import calcular_riego, analizar_economia
    from modules.rag_retriever   import RAGRetriever
    from modules.input_handler   import vocalizar_respuesta
    from modules                 import cli

    # ── Inicializar cliente LLM ──────────────────────────────────────────────
    ollama_cfg = cfg["ollama"]
    cliente = OllamaClient(
        host        = ollama_cfg["host"],
        model       = ollama_cfg["model"],
        timeout     = ollama_cfg["timeout"],
        num_predict = ollama_cfg["num_predict"],
        temperature = ollama_cfg["temperature"],
        stream      = ollama_cfg.get("stream", False),
    )

    # ── Inicializar base de datos ────────────────────────────────────────────
    from modules.persistence import AgriDatabase
    import os
    os.makedirs(os.path.dirname(cfg["base_datos"]["path"]), exist_ok=True)
    db = AgriDatabase(cfg["base_datos"]["path"])

    # ── Inicializar RAG ──────────────────────────────────────────────────────
    rag = None
    rag_cfg = cfg.get("rag", {})
    n_rag = rag_cfg.get("n_resultados", 1)   # Siempre 1 en Jetson 2 GB
    if rag_cfg.get("habilitado", False):
        rag = RAGRetriever(index_path=rag_cfg.get("index_path", "rag/index"))
        if rag.disponible:
            print(f"  RAG activo — fragmentos por consulta: {n_rag}")
        else:
            print("  AVISO: RAG no disponible.")
            print("  Ejecutar: python scripts/build_rag_index.py")
            rag = None

    # ── Verificar Ollama ─────────────────────────────────────────────────────
    print(f"\n  Verificando Ollama ({ollama_cfg['model']})...")
    if not cliente.health_check():
        print(
            f"\n  ERROR: Modelo '{ollama_cfg['model']}' no disponible.\n"
            f"  Si es la primera vez, ejecutar:\n"
            f"    ollama pull qwen2.5:3b\n"
            f"    ollama create agri-qwen3b -f data/models/Modelfile.agri\n"
            f"  Luego verificar con: ollama list"
        )
        sys.exit(1)
    print(f"  Ollama OK — {ollama_cfg['model']}")

    # ── Ciclo principal ──────────────────────────────────────────────────────
    while True:
        mostrar_menu()
        opcion = input("\n  Opcion: ").strip().lower()

        if opcion == "q":
            print("\n  Hasta luego.")
            break

        # ── Determinar modo y obtener descripción del agricultor ─────────────
        pregunta_libre = None

        if opcion == "1":
            modo = "diagnostico_fitosanitario"
            pregunta_libre = solicitar_texto(
                "\n  Describí los síntomas que ves en la planta\n"
                "  (ej: hojas con manchas negras, tallo blando, color amarillo):"
            )
            if not pregunta_libre:
                print("  Descripción vacía. Volviendo al menú.")
                continue
            print(f"  Modo: Diagnóstico fitosanitario")

        elif opcion == "2":
            modo = "riego_fertilizacion"
            pregunta_libre = solicitar_texto(
                "\n  ¿Cuál es tu consulta sobre riego y fertilización?:"
            )
            if not pregunta_libre:
                print("  Consulta vacía. Volviendo al menú.")
                continue
            print(f"  Modo: Riego y fertilización")

        elif opcion == "3":
            modo = "economia"
            pregunta_libre = solicitar_texto(
                "\n  ¿Cuál es tu consulta sobre análisis económico?:"
            )
            if not pregunta_libre:
                print("  Consulta vacía. Volviendo al menú.")
                continue
            print(f"  Modo: Análisis económico")

        elif opcion == "l":
            pregunta_libre = solicitar_texto("\n  ¿Cuál es tu consulta?:")
            if not pregunta_libre:
                print("  Consulta vacía. Volviendo al menú.")
                continue
            modo = detectar_modo(pregunta_libre)
            print(f"  Modo detectado: {modo.replace('_', ' ')}")
        else:
            print("  Opción inválida. Use 1, 2, 3, L o q.")
            continue

        # ── Etapa fenológica ─────────────────────────────────────────────────
        etapas = ["emergencia", "vegetativo", "tuberizacion", "maduracion"]
        print(f"\n  Etapas: {' | '.join(etapas)}")
        etapa_input = input("  Etapa fenológica (Enter = vegetativo): ").strip().lower()
        etapa = etapa_input if etapa_input in etapas else "vegetativo"

        # ── Datos según modo ─────────────────────────────────────────────────
        suelo  = {}
        costos = {}
        econ   = {}
        riego  = {}

        if modo in ("diagnostico_fitosanitario", "riego_fertilizacion"):
            suelo = cli.solicitar_datos_suelo()

        if modo == "riego_fertilizacion" and suelo:
            try:
                from modules.agri_logic import calcular_riego
                riego = calcular_riego(float(suelo.get("humedad_pct", 60)), etapa)
                print(f"  Riego calculado: {riego.get('frecuencia', 'N/A')}")
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
                logger.warning("Error en análisis económico: %s", e)

        # ── RAG ──────────────────────────────────────────────────────────────
        rag_fragmentos = []
        if rag:
            rag_fragmentos = rag.retrieve(pregunta_libre, n=n_rag)
            if not rag_fragmentos:
                rag_fragmentos = rag.retrieve_para_modo(modo)
            if rag_fragmentos:
                fuentes = ", ".join(f.get("fuente", "?") for f in rag_fragmentos)
                print(f"  RAG: {len(rag_fragmentos)} fragmento(s) — {fuentes}")

        # ── Construir contexto JSON ───────────────────────────────────────────
        # El modo para context_builder debe ser un modo agrícola válido.
        modo_contexto = modo if modo in (
            "diagnostico_fitosanitario", "riego_fertilizacion", "economia"
        ) else "diagnostico_fitosanitario"

        # El modo para el prompt puede ser consulta_libre si la pregunta es libre
        modo_prompt = "consulta_libre" if pregunta_libre else modo

        try:
            suelo_valido = suelo if suelo and any(v is not None for v in suelo.values()) else None
            ctx = build_context(
                modo            = modo_contexto,
                etapa_fenologica= etapa,
                suelo           = suelo_valido,
                vision_result   = None,     # Sin visión en esta versión
                costos          = costos or None,
                rag_fragmentos  = rag_fragmentos,
            )
            # Inyectar la pregunta del agricultor en el contexto
            if pregunta_libre:
                ctx["pregunta"] = pregunta_libre

        except ValueError as e:
            print(f"\n  ERROR en contexto: {e}")
            continue

        for advertencia in validate_context(ctx):
            logger.warning("Contexto: %s", advertencia)

        print("\n  --- CONTEXTO JSON ENVIADO AL LLM ---")
        print(context_to_json(ctx, indent=True))
        print("  ------------------------------------\n")

        # ── Liberar RAM antes del LLM ─────────────────────────────────────────
        # gc.collect() aquí es crítico en Jetson 2 GB: libera los buffers de
        # RAG y cualquier objeto intermedio antes de que Ollama necesite RAM
        # para el KV-cache.
        gc.collect()

        # ── LLM ──────────────────────────────────────────────────────────────
        prompt = build_llm_request(mode=modo_prompt, context=ctx)
        print("  Consultando al LLM...")
        resultado = cliente.generate(prompt)

        # Liberar prompt y contexto inmediatamente después de la llamada.
        # El KV-cache de Ollama ya no necesita el texto del prompt en Python.
        del prompt, ctx
        gc.collect()

        db.log_llm(modo, resultado)

        if not resultado["success"]:
            print(f"\n  ERROR LLM: {resultado['error']}")
            continue

        # ── Guardar en BD ─────────────────────────────────────────────────────
        try:
            if modo == "riego_fertilizacion" and riego:
                db.guardar_riego(etapa, suelo, riego, resultado["response"])
            elif modo == "economia" and econ:
                db.guardar_economia(econ, resultado["response"])
            # Nota: guardar_diagnostico se omite porque no hay visión
        except Exception as e:
            logger.warning("Error guardando en BD: %s", e)

        # ── Mostrar resultado ─────────────────────────────────────────────────
        cli.mostrar_resultado(resultado, modo)

        print(
            f"\n  [Latencia: {resultado['latency_s']:.1f}s | "
            f"Tokens entrada: {resultado['prompt_tokens']} | "
            f"Tokens salida: {resultado['response_tokens']}]"
        )

        # ── TTS: vocalizar respuesta ──────────────────────────────────────────
        # Se invoca DESPUÉS de gc.collect() para que Piper tenga el margen de
        # ~80 MB disponible durante los ~10 segundos que dura la síntesis.
        piper_cfg = cfg.get("piper", {})
        if piper_cfg.get("habilitado", False):
            if input("\n  ¿Vocalizar respuesta? [s/N]: ").strip().lower() == "s":
                resumen = resultado.get("resumen", "") or resultado.get("response", "")
                max_chars = piper_cfg.get("max_chars_tts", 200)
                vocalizar_respuesta(
                    texto      = resumen[:max_chars],
                    model_path = piper_cfg.get("model_path", ""),
                    bin_path   = piper_cfg.get("bin_path", "piper"),
                )

        if input("\n  ¿Otra consulta? [s/N]: ").strip().lower() != "s":
            print("\n  Hasta luego.")
            break

    db.close()


if __name__ == "__main__":
    main()