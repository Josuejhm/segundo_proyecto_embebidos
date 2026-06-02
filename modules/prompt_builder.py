"""
modules/prompt_builder.py
-------------------------
Ensambla el prompt final que se envía al LLM.

Responsabilidades:
  - Cargar la plantilla de prompt según el modo activo.
  - Inyectar el contexto JSON en la plantilla.
  - Exponer la función central build_llm_request().

Regla obligatoria:
  NUNCA llamar al LLM desde main.py con texto libre.
  Toda llamada debe pasar por:
    1. context_builder.py → genera el dict de contexto
    2. prompt_builder.py  → arma el prompt final
    3. llm_client.py      → envía el prompt a Ollama

CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
  - Fallback de consulta_libre estaba mezclado con inglés → reescrito en español
  - Todos los fallbacks usan "sos/respondés" (español costarricense)
  - prompts/consulta_libre.md creado con formato correcto
  - _log_checklist ampliado: verifica que {contexto_json} fue reemplazado
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio base de plantillas de prompt
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Mapeo modo → archivo de plantilla
PROMPT_FILES = {
    "diagnostico_fitosanitario": "diagnostico_fitosanitario.md",
    "riego_fertilizacion":       "riego_fertilizacion.md",
    "economia":                  "economia.md",
    "consulta_libre":            "consulta_libre.md",
}

# ── Plantillas inline de respaldo ────────────────────────────────────────────
# Se usan SOLO si el archivo .md no existe (por ejemplo, en primera ejecución
# antes de que la imagen Yocto incluya la carpeta prompts/).
# Mantener sincronizadas con los archivos .md correspondientes.

PROMPT_FALLBACK = {
    "diagnostico_fitosanitario": (
        "Sos un asistente agrícola especializado en el cultivo de papa en Costa Rica.\n"
        "Respondés en español costarricense claro y breve.\n"
        "Usás únicamente el contexto JSON proporcionado. No inventás datos.\n"
        "Devolvés primero un JSON válido con los campos:\n"
        "  diagnostico, enfermedad_detectada, severidad,\n"
        "  recomendaciones (lista), nivel_urgencia (bajo|medio|alto|critico).\n"
        "Después del JSON escribís un resumen corto en lenguaje simple.\n"
        "Aclarás que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
    "riego_fertilizacion": (
        "Sos un asistente agrícola especializado en el cultivo de papa en Costa Rica.\n"
        "Respondés en español costarricense claro y breve.\n"
        "Usás únicamente el contexto JSON proporcionado. No inventás datos.\n"
        "Devolvés primero un JSON válido con los campos:\n"
        "  riego (frecuencia, volumen_litros_por_planta, proxima_aplicacion),\n"
        "  fertilizacion (tipo, dosis, frecuencia),\n"
        "  advertencias (lista).\n"
        "Después del JSON escribís un resumen corto para el agricultor.\n"
        "Aclarás que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
    "economia": (
        "Sos un asistente agrícola especializado en el cultivo de papa en Costa Rica.\n"
        "Respondés en español costarricense claro y breve.\n"
        "Usás únicamente el contexto JSON proporcionado. No inventás datos.\n"
        "Devolvés primero un JSON válido con los campos:\n"
        "  precio_esperado_crc_kg, margen_estimado_crc, punto_equilibrio_kg,\n"
        "  recomendacion_venta (vender_ahora|esperar|negociar), justificacion.\n"
        "Después del JSON escribís un resumen corto para el agricultor.\n"
        "Aclarás que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
    "consulta_libre": (
        "Sos un asistente agrícola especializado en el cultivo de papa en Costa Rica.\n"
        "Respondés en español costarricense claro, usando vocabulario comprensible\n"
        "para agricultores con educación técnica media.\n"
        "Usás únicamente la información del contexto JSON. No inventás datos.\n"
        "Si no tenés información suficiente, lo decís claramente.\n\n"
        "Devolvés primero un JSON válido con exactamente esta estructura:\n"
        "{\"respuesta\": \"string\", \"fuentes_usadas\": [\"string\"], \"nota\": \"string\"}\n\n"
        "Después del JSON escribís 2-3 oraciones de resumen en lenguaje simple.\n"
        "Aclarás que para decisiones importantes conviene consultar con un agrónomo del INTA.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
}


# ── API pública ──────────────────────────────────────────────────────────────

def build_llm_request(mode: str, context: dict) -> str:
    """
    Construye el prompt final que será enviado al LLM.

    Args:
        mode:    Modo activo (diagnostico_fitosanitario | riego_fertilizacion |
                 economia | consulta_libre).
        context: Dict de contexto generado por context_builder.build_context().

    Returns:
        String con el prompt completo listo para enviar a Ollama.

    Raises:
        ValueError: Si el modo no tiene plantilla definida.
    """
    if mode not in PROMPT_FILES:
        modos_validos = list(PROMPT_FILES.keys())
        raise ValueError(
            f"Modo '{mode}' sin plantilla de prompt. "
            f"Modos válidos: {modos_validos}"
        )

    contexto_json = json.dumps(context, ensure_ascii=False, indent=2)
    plantilla = _cargar_plantilla(mode)
    prompt = plantilla.replace("{contexto_json}", contexto_json)

    logger.debug("Prompt construido para modo '%s' — %d chars.", mode, len(prompt))
    _log_checklist(prompt, contexto_json, mode)
    return prompt


# ── Carga de plantillas ──────────────────────────────────────────────────────

def _cargar_plantilla(mode: str) -> str:
    """
    Carga plantilla desde archivo .md; usa fallback inline si no existe.

    Orden de prioridad:
      1. prompts/<modo>.md  (archivo en disco — el canónico)
      2. PROMPT_FALLBACK[mode] (inline — para primera ejecución sin archivos)
    """
    ruta = PROMPTS_DIR / PROMPT_FILES[mode]
    if ruta.exists():
        texto = ruta.read_text(encoding="utf-8").strip()
        logger.debug("Plantilla cargada desde: %s", ruta)
        return texto

    logger.warning(
        "Plantilla '%s' no encontrada en disco. Usando fallback inline.\n"
        "  → Verificá que la carpeta prompts/ esté presente en el proyecto.",
        ruta,
    )
    return PROMPT_FALLBACK[mode]


# ── Checklist de validación ──────────────────────────────────────────────────

def _log_checklist(prompt: str, contexto_json: str, mode: str) -> None:
    """Registra en DEBUG el checklist de validación antes de enviar al LLM."""
    checks = {
        "Contexto JSON válido":           _es_json_valido(contexto_json),
        "Prompt no vacío":                bool(prompt.strip()),
        "Placeholder reemplazado":        "{contexto_json}" not in prompt,
        "Incluye nota seguridad/agrónomo": (
            "agrónomo" in prompt.lower()
            or "orientativa" in prompt.lower()
            or "inta" in prompt.lower()
        ),
        "Tamaño prompt < 4000 chars":     len(prompt) < 4000,
        "Modo válido":                    mode in PROMPT_FILES,
    }
    for check, estado in checks.items():
        nivel = logging.DEBUG if estado else logging.WARNING
        logger.log(nivel, "[CHECKLIST] %s: %s", check, "✓" if estado else "✗ FALLO")


def _es_json_valido(texto: str) -> bool:
    try:
        json.loads(texto)
        return True
    except Exception:
        return False