"""
modules/prompt_builder.py — v5
"""
import json, logging
from pathlib import Path

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = {
    "diagnostico_fitosanitario": "diagnostico_fitosanitario.md",
    "riego_fertilizacion":       "riego_fertilizacion.md",
    "economia":                  "economia.md",
    "consulta_libre":            "consulta_libre.md",
}

_D = '"'  # comilla doble para los JSON dentro de los strings

PROMPT_FALLBACK = {
    "diagnostico_fitosanitario": "\n".join([
        "MODO: Diagnostico papa Costa Rica. Sin internet. Sin camara.",
        "Respondés en español. Usás SOLO el contexto JSON.",
        "",
        "TU RESPUESTA SIEMPRE EMPIEZA CON { Y TERMINA CON }",
        "",
        'EJEMPLO: {"causa":"tizon tardio Phytophthora infestans","urgencia":"critico","accion":"aplicar fungicida de cobre","nota":"consulte agronomo hoy"}',
        "",
        "REGLA: En causa ponés el NOMBRE de la enfermedad, nunca el texto del síntoma.",
        'REGLA: manchas negras+humedad→causa:"tizon tardio Phytophthora infestans",urgencia:"critico"',
        'REGLA: pudricion→causa:"fusariosis Fusarium solani",urgencia:"alto"',
        'REGLA: amarillamiento sin manchas→causa:"deficiencia nutricional posible",urgencia:"medio"',
        "REGLA: Usás tizón en español, nunca blight.",
        "",
        'SIN pregunta: {"causa":"sin datos","urgencia":"bajo","accion":"Describa sintomas visibles","nota":"sin sintomas no diagnostico"}',
        "",
        "Luego 1-2 oraciones. Final: Consulte agronomo.",
        "",
        "CONTEXTO:",
        "{contexto_json}",
        "",
        "RESPUESTA:",
    ]),

    "riego_fertilizacion": "\n".join([
        "MODO: Riego fertilizacion papa Costa Rica. Sin internet.",
        "Respondés en español. Usás SOLO el contexto JSON.",
        "",
        'FORMATO 4 campos: {"frecuencia":"dias o inmediato hoy","urgencia":"baja|media|alta|desconocido","fertilizacion":"producto o ninguna","nota":"advertencia"}',
        "REGLA urgencia: humedad<40→alta. 40-60→media. >60→baja. null→desconocido",
        "REGLA fertilizacion: tuberizacion+potasio bajo→cloruro potasio 150kg/ha. vegetativo+nitrogeno bajo→urea 150kg/ha",
        'SIN humedad: {"frecuencia":"sin datos","urgencia":"desconocido","fertilizacion":"sin datos","nota":"mida humedad primero"}',
        "",
        "Luego 1-2 oraciones. Final: Consulte agronomo.",
        "",
        "CONTEXTO:",
        "{contexto_json}",
        "",
        "RESPUESTA:",
    ]),

    "economia": "\n".join([
        "MODO: Economia papa Costa Rica. Sin internet.",
        "Respondés en español. NUNCA inventás números.",
        "",
        'FORMATO 4 campos: {"margen":NUMERO,"decision":"vender_ahora|esperar|negociar|no_rentable|sin datos","precio_kg":NUMERO,"nota":"justificacion"}',
        "REGLA1: costos vacío→decision:sin datos,margen:0,precio_kg:0",
        "REGLA2: margen_estimado_crc NEGATIVO(<0)→decision:no_rentable PRIORIDAD",
        "REGLA3: margen<20pct costo→negociar. margen>=20pct→vender_ahora",
        "REGLA4: margen=valor exacto de costos.margen_estimado_crc. precio_kg=costos.precio_referencia_crc_kg",
        'SIN costos: {"margen":0,"decision":"sin datos","precio_kg":0,"nota":"ingrese costos"}',
        "",
        "Luego 1-2 oraciones. Final: precios varían semanalmente.",
        "",
        "CONTEXTO:",
        "{contexto_json}",
        "",
        "RESPUESTA:",
    ]),

    "consulta_libre": "\n".join([
        "MODO: Consulta libre papa Costa Rica. Sin internet.",
        "Respondés en español. Usás SOLO el contexto JSON.",
        "",
        'FORMATO 3 campos: {"respuesta":"1-2 oraciones","fuente":"RAG o conocimiento base","nota":"advertencia o ninguna"}',
        'SIN datos: {"respuesta":"No tengo datos suficientes.","fuente":"ninguna","nota":"ninguna"}',
        "",
        "Luego 1-2 oraciones. Final: Consulta con tecnico del INTA.",
        "",
        "CONTEXTO:",
        "{contexto_json}",
        "",
        "RESPUESTA:",
    ]),
}


def build_llm_request(mode: str, context: dict) -> str:
    if mode not in PROMPT_FILES:
        raise ValueError(f"Modo '{mode}' inválido. Válidos: {list(PROMPT_FILES.keys())}")
    contexto_json = json.dumps(context, ensure_ascii=False, indent=2)
    plantilla     = _cargar_plantilla(mode)
    prompt        = plantilla.replace("{contexto_json}", contexto_json)
    logger.debug("Prompt modo='%s' — %d chars.", mode, len(prompt))
    _log_checklist(prompt, contexto_json, mode)
    return prompt


def _cargar_plantilla(mode: str) -> str:
    ruta = PROMPTS_DIR / PROMPT_FILES[mode]
    if ruta.exists():
        texto = ruta.read_text(encoding="utf-8").strip()
        logger.debug("Plantilla desde disco: %s", ruta)
        return texto
    logger.warning("Plantilla '%s' no encontrada. Usando fallback.", ruta)
    return PROMPT_FALLBACK[mode]


def _log_checklist(prompt, contexto_json, mode):
    checks = {
        "JSON válido":             _es_json_valido(contexto_json),
        "Prompt no vacío":         bool(prompt.strip()),
        "Placeholder reemplazado": "{contexto_json}" not in prompt,
        "Anchor RESPUESTA":        "RESPUESTA:" in prompt,
        "Tamaño < 3000 chars":     len(prompt) < 3000,
    }
    for k, ok in checks.items():
        logger.log(logging.DEBUG if ok else logging.WARNING,
                   "[CHECKLIST] %s: %s", k, "✓" if ok else "✗ FALLO")


def _es_json_valido(texto):
    try: json.loads(texto); return True
    except: return False