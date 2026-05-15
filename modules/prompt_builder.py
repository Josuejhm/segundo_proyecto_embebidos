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
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio base de plantillas de prompt
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Mapeo modo → archivo de plantilla
PROMPT_FILES = {
    "diagnostico_fitosanitario": "diagnostico_fitosanitario.md",
    "riego_fertilizacion": "riego_fertilizacion.md",
    "economia": "economia.md",
}

# Plantillas inline de respaldo (si no se encuentra el archivo .md)
PROMPT_FALLBACK = {
    "diagnostico_fitosanitario": (
        "Eres un asistente agrícola offline para productores de papa en Costa Rica.\n"
        "Usa únicamente el contexto JSON proporcionado.\n"
        "No inventes datos que no estén en el contexto.\n"
        "Responde en español claro y breve.\n"
        "Devuelve primero un JSON válido con los campos: "
        "diagnostico, enfermedad_detectada, severidad, recomendaciones (lista), "
        "nivel_urgencia (bajo|medio|alto|critico).\n"
        "Luego escribe un resumen corto en lenguaje simple para el agricultor.\n"
        "Aclara que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
    "riego_fertilizacion": (
        "Eres un asistente agrícola offline para productores de papa en Costa Rica.\n"
        "Usa únicamente el contexto JSON proporcionado.\n"
        "No inventes datos que no estén en el contexto.\n"
        "Responde en español claro y breve.\n"
        "Devuelve primero un JSON válido con los campos: "
        "riego (frecuencia, volumen_litros_por_planta, proxima_aplicacion), "
        "fertilizacion (tipo, dosis, frecuencia), advertencias (lista).\n"
        "Luego escribe un resumen corto para el agricultor.\n"
        "Aclara que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
    "economia": (
        "Eres un asistente agrícola offline para productores de papa en Costa Rica.\n"
        "Usa únicamente el contexto JSON proporcionado.\n"
        "No inventes datos que no estén en el contexto.\n"
        "Responde en español claro y breve.\n"
        "Devuelve primero un JSON válido con los campos: "
        "precio_esperado_crc_kg, margen_estimado_crc, punto_equilibrio_kg, "
        "recomendacion_venta (vender_ahora|esperar|negociar), justificacion.\n"
        "Luego escribe un resumen corto para el agricultor.\n"
        "Aclara que la recomendación es orientativa y no sustituye a un agrónomo.\n\n"
        "CONTEXTO:\n{contexto_json}"
    ),
}


def build_llm_request(mode: str, context: dict) -> str:
    """
    Construye el prompt final que será enviado al LLM.

    Args:
        mode: Modo activo (diagnostico_fitosanitario | riego_fertilizacion | economia).
        context: Dict de contexto generado por context_builder.build_context().

    Returns:
        String con el prompt completo listo para enviar a Ollama.
    """
    if mode not in PROMPT_FILES:
        raise ValueError(f"Modo '{mode}' sin plantilla de prompt.")

    contexto_json = json.dumps(context, ensure_ascii=False, indent=2)
    plantilla = _cargar_plantilla(mode)
    prompt = plantilla.replace("{contexto_json}", contexto_json)

    logger.debug("Prompt construido para modo '%s' — %d chars.", mode, len(prompt))
    _log_checklist(prompt, contexto_json)
    return prompt


def _cargar_plantilla(mode: str) -> str:
    """Carga plantilla desde archivo .md; usa fallback si no existe."""
    ruta = PROMPTS_DIR / PROMPT_FILES[mode]
    if ruta.exists():
        texto = ruta.read_text(encoding="utf-8").strip()
        logger.debug("Plantilla cargada desde: %s", ruta)
        return texto
    else:
        logger.warning("Plantilla '%s' no encontrada. Usando fallback inline.", ruta)
        return PROMPT_FALLBACK[mode]


def _log_checklist(prompt: str, contexto_json: str) -> None:
    """Registra en DEBUG el checklist de validación antes de enviar al LLM."""
    checks = {
        "JSON contexto válido": _es_json_valido(contexto_json),
        "Prompt no vacío": bool(prompt.strip()),
        "Incluye nota seguridad": "agrónomo" in prompt.lower() or "orientativa" in prompt.lower(),
        "Tamaño prompt < 3000 chars": len(prompt) < 3000,
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
