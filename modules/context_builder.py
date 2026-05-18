"""
modules/context_builder.py
--------------------------
Construye el contexto JSON compacto que se inyecta en cada llamada al LLM.

CAMBIO PRINCIPAL respecto a versión anterior: integración del RAG.
  Versión anterior: el contexto no tenía información local de Costa Rica.
  Versión actual:   agrega campo 'contexto_local_cr' con fragmentos
                    recuperados de los documentos en rag/documentos/.

  RAZÓN: qwen2.5:3b (como cualquier modelo pequeño offline) no conoce:
    - Precios PIMA actuales en colones
    - Variedades locales de papa (La Floresta)
    - Productos SENASA autorizados en CR
    - Condiciones climáticas de Tierra Blanca de Cartago
  Con el RAG, la aplicación recupera esa información y la inyecta aquí.

RESTRICCIÓN JETSON:
  El contexto total (incluyendo fragmentos RAG) debe mantenerse bajo
  1500 caracteres para que el prompt no supere ~500 tokens.
  Más de 500 tokens de entrada → el LLM tarda más de 30s en Jetson.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MODOS_VALIDOS = {"diagnostico_fitosanitario", "riego_fertilizacion", "economia"}
ETAPAS_VALIDAS = {"emergencia", "vegetativo", "tuberizacion", "maduracion"}

CULTIVO_DEFAULT = {
    "tipo": "papa",
    "variedad": "La Floresta",
    "ubicacion": "Tierra Blanca de Cartago, Costa Rica",
}


def build_context(
    modo: str,
    etapa_fenologica: str,
    suelo: Optional[dict] = None,
    vision_result: Optional[dict] = None,
    costos: Optional[dict] = None,
    cultivo_override: Optional[dict] = None,
    rag_fragmentos: Optional[list] = None,
) -> dict:
    """
    Construye y valida el contexto JSON para el LLM.

    Args:
        modo:              Modo activo del sistema.
        etapa_fenologica:  Estado fenológico del cultivo.
        suelo:             Dict con humedad_pct, ph, nitrogeno, fosforo, potasio.
        vision_result:     Resultado del módulo de visión (real o mock).
        costos:            Dict con datos económicos (modo economia).
        cultivo_override:  Sobreescribir campos del cultivo por defecto.
        rag_fragmentos:    Lista de dicts {'fuente':str, 'texto':str}
                           del RAGRetriever. None = funciona sin RAG.

    Returns:
        Dict con el contexto listo para serializar como JSON.

    Raises:
        ValueError si modo o etapa son inválidos.
    """
    _validar(modo, etapa_fenologica)

    cultivo = {**CULTIVO_DEFAULT, "etapa_fenologica": etapa_fenologica}
    if cultivo_override:
        cultivo.update(cultivo_override)

    ctx: dict = {
        "modo": modo,
        "cultivo": cultivo,
    }

    # ── Datos específicos por modo ───────────────────────────────────────────
    if modo == "diagnostico_fitosanitario":
        ctx["suelo"] = _normalizar_suelo(suelo)
        ctx["vision"] = vision_result if vision_result else _vision_sin_datos()

    elif modo == "riego_fertilizacion":
        ctx["suelo"] = _normalizar_suelo(suelo)

    elif modo == "economia":
        ctx["costos"] = costos or {}

    # ── Fragmentos RAG ───────────────────────────────────────────────────────
    # Máximo 2 fragmentos, cada uno truncado a 250 chars.
    # RAZÓN DEL LÍMITE:
    #   Cada fragmento agrega ~60-80 tokens al prompt.
    #   Con n=2 el overhead es ~120-160 tokens, aceptable en Jetson.
    #   Con n=3 o textos largos se supera el presupuesto de RAM del LLM.
    if rag_fragmentos:
        ctx["contexto_local_cr"] = [
            {
                "fuente": f["fuente"],
                "info": f["texto"][:250],
            }
            for f in rag_fragmentos[:2]
        ]

    total_chars = len(json.dumps(ctx, ensure_ascii=False))
    logger.debug(
        "Contexto construido — modo=%s chars=%d rag_fragmentos=%d",
        modo, total_chars, len(rag_fragmentos or []),
    )

    return ctx


def context_to_json(ctx: dict, indent: bool = False) -> str:
    """Serializa el contexto a JSON compacto o legible."""
    return json.dumps(ctx, ensure_ascii=False, indent=2 if indent else None)


def validate_context(ctx: dict) -> list:
    """
    Valida el contexto y retorna lista de advertencias.
    Retorna lista vacía si todo está correcto.
    """
    advertencias = []

    if ctx.get("modo") not in MODOS_VALIDOS:
        advertencias.append(f"Modo inválido: {ctx.get('modo')}")

    if "cultivo" not in ctx:
        advertencias.append("Falta sección 'cultivo'.")

    if (ctx.get("modo") == "diagnostico_fitosanitario"
            and "vision" not in ctx):
        advertencias.append("Modo diagnóstico sin datos de visión.")

    total_chars = len(json.dumps(ctx, ensure_ascii=False))
    if total_chars > 1500:
        advertencias.append(
            f"Contexto largo ({total_chars} chars). "
            "Puede presionar tokens en Jetson. "
            "Reducir campos RAG o datos de suelo."
        )

    return advertencias


# ── Helpers privados ─────────────────────────────────────────────────────────

def _normalizar_suelo(suelo: Optional[dict]) -> dict:
    """Retorna suelo con valores por defecto para campos faltantes."""
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
    """Retorna un resultado de visión vacío cuando no hay imagen."""
    return {
        "health_category": "desconocido",
        "disease_detected": "no evaluado",
        "severity_index": None,
        "confidence": None,
        "observations": ["Sin imagen disponible."],
    }


def _validar(modo: str, etapa: str) -> None:
    if modo not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo '{modo}' inválido. Válidos: {MODOS_VALIDOS}"
        )
    if etapa not in ETAPAS_VALIDAS:
        raise ValueError(
            f"Etapa '{etapa}' inválida. Válidas: {ETAPAS_VALIDAS}"
        )