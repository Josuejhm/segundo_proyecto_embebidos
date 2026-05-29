"""
modules/prompt_builder.py — v4
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

PROMPT_FILES = {
    "diagnostico_fitosanitario": "diagnostico_fitosanitario.md",
    "riego_fertilizacion":       "riego_fertilizacion.md",
    "economia":                  "economia.md",
    "consulta_libre":            "consulta_libre.md",
}

PROMPT_FALLBACK = {
    "diagnostico_fitosanitario": (
        "Sos asistente agrícola para papa en Costa Rica. Sin internet. Sin camara.\n"
        "Respondés ÚNICAMENTE en español costarricense.\n"
        "Usás SOLO el contexto JSON. NUNCA inventás enfermedades.\n\n"
        "FORMATO OBLIGATORIO — exactamente 4 campos:\n"
        "{\"causa\":\"NOMBRE ENFERMEDAD\",\"urgencia\":\"bajo|medio|alto|critico\","
        "\"accion\":\"que hacer\",\"nota\":\"advertencia\"}\n\n"
        "En 'causa' ponés el NOMBRE DE LA ENFERMEDAD, nunca el texto del síntoma.\n"
        "SI no hay campo 'pregunta', respondé: "
        "{\"causa\":\"sin datos\",\"urgencia\":\"bajo\","
        "\"accion\":\"Describa los sintomas\",\"nota\":\"Sin descripcion no es posible diagnosticar\"}\n\n"
        "manchas negras+humedad → tizon tardio Phytophthora infestans\n"
        "pudricion → fusariosis Fusarium solani\n\n"
        "CONTEXTO:\n{contexto_json}\n\nRESPUESTA:"
    ),
    "riego_fertilizacion": (
        "Sos asistente agrícola para papa en Costa Rica. Sin internet.\n"
        "Respondés ÚNICAMENTE en español costarricense.\n"
        "Usás SOLO el contexto JSON. NUNCA inventás valores.\n\n"
        "FORMATO OBLIGATORIO — exactamente 4 campos:\n"
        "{\"frecuencia\":\"cada N dias o inmediato hoy\",\"urgencia\":\"baja|media|alta|desconocido\","
        "\"fertilizacion\":\"producto o ninguna\",\"nota\":\"advertencia\"}\n\n"
        "SI humedad_pct es null: {\"frecuencia\":\"sin datos\",\"urgencia\":\"desconocido\","
        "\"fertilizacion\":\"sin datos\",\"nota\":\"Mida la humedad primero\"}\n\n"
        "REGLA urgencia: humedad<40→alta, 40-60→media, >60→baja, null→desconocido\n\n"
        "CONTEXTO:\n{contexto_json}\n\nRESPUESTA:"
    ),
    "economia": (
        "Sos asistente agrícola para papa en Costa Rica. Sin internet.\n"
        "Respondés ÚNICAMENTE en español costarricense.\n"
        "Usás SOLO números del contexto JSON. NUNCA inventás cifras.\n\n"
        "FORMATO OBLIGATORIO — exactamente 4 campos:\n"
        "{\"margen\":NUMERO,\"decision\":\"vender_ahora|esperar|negociar|no_rentable|sin datos\","
        "\"precio_kg\":NUMERO,\"nota\":\"justificacion\"}\n\n"
        "SI costos vacío: {\"margen\":0,\"decision\":\"sin datos\",\"precio_kg\":0,"
        "\"nota\":\"Ingrese los costos del ciclo\"}\n\n"
        "REGLAS decision (en orden): costos vacío→sin datos. "
        "margen_estimado_crc<0(NEGATIVO)→no_rentable. "
        "margen<20pct costo→negociar. margen>=20pct→vender_ahora.\n"
        "margen en respuesta = valor exacto de costos.margen_estimado_crc del contexto.\n\n"
        "CONTEXTO:\n{contexto_json}\n\nRESPUESTA:"
    ),
    "consulta_libre": (
        "Sos asistente agrícola para papa en Costa Rica. Sin internet.\n"
        "Respondés ÚNICAMENTE en español costarricense.\n"
        "Usás SOLO el contexto JSON. NUNCA inventás datos.\n\n"
        "FORMATO OBLIGATORIO — exactamente 3 campos:\n"
        "{\"respuesta\":\"en 1-2 oraciones\",\"fuente\":\"RAG o conocimiento base\","
        "\"nota\":\"advertencia o ninguna\"}\n\n"
        "SI no tenés datos: {\"respuesta\":\"No tengo datos suficientes.\","
        "\"fuente\":\"ninguna\",\"nota\":\"ninguna\"}\n\n"
        "CONTEXTO:\n{contexto_json}\n\nRESPUESTA:"
    ),
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


def _log_checklist(prompt: str, contexto_json: str, mode: str) -> None:
    checks = {
        "Contexto JSON válido":       _es_json_valido(contexto_json),
        "Prompt no vacío":            bool(prompt.strip()),
        "Placeholder reemplazado":    "{contexto_json}" not in prompt,
        "Anchor RESPUESTA presente":  "RESPUESTA:" in prompt,
        "Incluye nota agrónomo/INTA": (
            "agronomo" in prompt.lower()
            or "agrónomo" in prompt.lower()
            or "inta" in prompt.lower()
        ),
        "Tamaño < 3000 chars":        len(prompt) < 3000,
    }
    for check, ok in checks.items():
        nivel = logging.DEBUG if ok else logging.WARNING
        logger.log(nivel, "[CHECKLIST] %s: %s", check, "✓" if ok else "✗ FALLO")


def _es_json_valido(texto: str) -> bool:
    try:
        json.loads(texto)
        return True
    except Exception:
        return False