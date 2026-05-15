"""
modules/context_builder.py
--------------------------
Construye el contexto JSON compacto que se inyecta en cada llamada al LLM.

Regla fundamental:
  El LLM NUNCA recibe texto libre sin contexto.
  Todo prompt incluye un contexto JSON generado aquí.

El contexto incluye SOLO los datos relevantes al modo activo para respetar
el límite de tokens y la RAM disponible en el Jetson Nano.

Modos soportados:
  - diagnostico_fitosanitario
  - riego_fertilizacion
  - economia
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Modos válidos del sistema
MODOS_VALIDOS = {"diagnostico_fitosanitario", "riego_fertilizacion", "economia"}

# Valores por defecto del cultivo (editables en settings.yaml)
CULTIVO_DEFAULT = {
    "tipo": "papa",
    "variedad": "La Floresta",
    "ubicacion": "Cartago, Costa Rica",
}

# Restricciones de respuesta comunes
RESTRICCIONES_DEFAULT = {
    "idioma": "español costarricense claro",
    "formato": "json_mas_resumen",
    "max_tokens": 250,
    "incluir_nota_seguridad": True,
}


def build_context(
    modo: str,
    etapa_fenologica: str,
    suelo: Optional[dict] = None,
    vision_result: Optional[dict] = None,
    costos: Optional[dict] = None,
    cultivo_override: Optional[dict] = None,
    restricciones_override: Optional[dict] = None,
) -> dict:
    """
    Construye y valida el contexto JSON para el LLM.

    Args:
        modo: Uno de MODOS_VALIDOS.
        etapa_fenologica: Estado actual del cultivo (emergencia|vegetativo|tuberizacion|maduracion).
        suelo: Dict con humedad_pct, ph, nitrogeno, fosforo, potasio.
        vision_result: Resultado del módulo F2 (real o mock).
        costos: Dict con costos_operacionales, rendimiento_esperado_kg (para modo economia).
        cultivo_override: Sobreescribir campos del cultivo por defecto.
        restricciones_override: Sobreescribir restricciones de respuesta.

    Returns:
        Dict con el contexto JSON listo para inyectar en el prompt.

    Raises:
        ValueError si el modo o etapa no son válidos.
    """

    _validar_modo(modo)
    _validar_etapa(etapa_fenologica)

    cultivo = {**CULTIVO_DEFAULT, "etapa_fenologica": etapa_fenologica}
    if cultivo_override:
        cultivo.update(cultivo_override)

    restricciones = {**RESTRICCIONES_DEFAULT}
    if restricciones_override:
        restricciones.update(restricciones_override)

    ctx: dict = {
        "modo": modo,
        "cultivo": cultivo,
        "restricciones_respuesta": restricciones,
    }

    # --- Datos específicos por modo ---
    if modo == "diagnostico_fitosanitario":
        ctx["suelo"] = _normalizar_suelo(suelo)
        if vision_result:
            ctx["vision"] = vision_result
        else:
            logger.warning("diagnostico_fitosanitario sin resultado de visión; se usarán defaults.")
            ctx["vision"] = _vision_sin_datos()

    elif modo == "riego_fertilizacion":
        ctx["suelo"] = _normalizar_suelo(suelo)

    elif modo == "economia":
        ctx["costos"] = costos or {}

    logger.debug("Contexto construido para modo '%s': %d campos.", modo, len(ctx))
    return ctx


def context_to_json(ctx: dict, indent: bool = False) -> str:
    """Serializa el contexto a JSON compacto o legible."""
    return json.dumps(ctx, ensure_ascii=False, indent=2 if indent else None)


def validate_context(ctx: dict) -> list[str]:
    """
    Valida el contexto y retorna lista de advertencias.
    Retorna lista vacía si todo está bien.
    """
    warnings = []

    if "modo" not in ctx:
        warnings.append("Falta campo 'modo'.")
    elif ctx["modo"] not in MODOS_VALIDOS:
        warnings.append(f"Modo inválido: {ctx['modo']}.")

    if "cultivo" not in ctx:
        warnings.append("Falta sección 'cultivo'.")

    if ctx.get("modo") == "diagnostico_fitosanitario" and "vision" not in ctx:
        warnings.append("Modo diagnóstico sin datos de visión.")

    # Verificar que el JSON no sea demasiado grande para Jetson (>2000 chars = riesgo)
    json_len = len(json.dumps(ctx))
    if json_len > 2000:
        warnings.append(f"Contexto largo ({json_len} chars); puede presionar tokens en Jetson.")

    return warnings


# ------------------------------------------------------------------
# Helpers privados
# ------------------------------------------------------------------

def _normalizar_suelo(suelo: Optional[dict]) -> dict:
    defaults = {
        "humedad_pct": None,
        "ph": None,
        "nitrogeno": "desconocido",
        "fosforo": "desconocido",
        "potasio": "desconocido",
    }
    if suelo:
        defaults.update(suelo)
    return defaults


def _vision_sin_datos() -> dict:
    return {
        "health_category": "desconocido",
        "disease_detected": "no evaluado",
        "severity_index": None,
        "confidence": None,
        "observations": ["Sin imagen disponible; basarse en datos de suelo y etapa."],
    }


def _validar_modo(modo: str) -> None:
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"Modo '{modo}' inválido. Modos válidos: {MODOS_VALIDOS}")


def _validar_etapa(etapa: str) -> None:
    etapas = {"emergencia", "vegetativo", "tuberizacion", "maduracion"}
    if etapa not in etapas:
        raise ValueError(f"Etapa '{etapa}' inválida. Etapas válidas: {etapas}")
