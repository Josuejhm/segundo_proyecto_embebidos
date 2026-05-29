"""
modules/context_builder.py
--------------------------
Construye el contexto JSON compacto que se inyecta en cada llamada al LLM.

CAMBIOS EN ESTA VERSIÓN (adaptación Jetson 2 GB sin visión):

1. VISIÓN YA NO ES OBLIGATORIA EN diagnostico_fitosanitario:
   - Antes: vision_result=None insertaba un bloque vacío pero presente.
   - Ahora: vision_result siempre es None (módulo eliminado). El contexto
     de diagnóstico se basa en la descripción textual del agricultor y
     en los fragmentos RAG de enfermedades de papa en Costa Rica.
   - El campo "vision" se mantiene en el JSON pero con estado="sin_camara"
     para que el prompt sepa que no hay imagen disponible y no pida una.

2. FRAGMENTOS RAG TRUNCADOS A 150 CARACTERES (antes 250):
   - Razón: con qwen2.5:3b Q3_K_M y num_ctx=512, el presupuesto de tokens
     es muy ajustado. 150 chars ≈ 35-40 tokens por fragmento.
   - 250 chars → ~60 tokens → con n=1 el prompt puede superar 220 tokens.
   - 150 chars → ~37 tokens → prompt seguro en ~190 tokens.

3. ADVERTENCIA DE CONTEXTO REDUCIDA A 800 CHARS:
   - El límite anterior de 1500 era para Jetson 4 GB con modelos más grandes.
   - Con num_ctx=512, el prompt completo (plantilla + contexto) debe caber
     en ~400 tokens. 800 chars de contexto JSON ≈ 200 tokens.

4. validate_context() YA NO ADVIERTE sobre visión faltante:
   - En esta versión es esperado y correcto que no haya datos de visión.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MODOS_VALIDOS  = {"diagnostico_fitosanitario", "riego_fertilizacion", "economia"}
ETAPAS_VALIDAS = {"emergencia", "vegetativo", "tuberizacion", "maduracion"}

CULTIVO_DEFAULT = {
    "tipo":      "papa",
    "variedad":  "La Floresta",
    "ubicacion": "Tierra Blanca de Cartago, Costa Rica",
}


def build_context(
    modo:              str,
    etapa_fenologica:  str,
    suelo:             Optional[dict] = None,
    vision_result:     Optional[dict] = None,   # Siempre None en esta versión
    costos:            Optional[dict] = None,
    cultivo_override:  Optional[dict] = None,
    rag_fragmentos:    Optional[list] = None,
) -> dict:
    """
    Construye y valida el contexto JSON para el LLM.

    Args:
        modo:              Modo activo del sistema.
        etapa_fenologica:  Estado fenológico del cultivo.
        suelo:             Dict con humedad_pct, ph, nitrogeno, fosforo, potasio.
        vision_result:     Siempre None en esta versión (visión eliminada).
        costos:            Dict con datos económicos (modo economia).
        cultivo_override:  Sobreescribir campos del cultivo por defecto.
        rag_fragmentos:    Lista de dicts con fragmentos del RAGRetriever.

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
        "modo":    modo,
        "cultivo": cultivo,
    }

    # ── Datos específicos por modo ───────────────────────────────────────────
    if modo == "diagnostico_fitosanitario":
        ctx["suelo"] = _normalizar_suelo(suelo)
        # En esta versión no hay cámara: se informa al LLM para que
        # base el diagnóstico en la descripción textual del agricultor.
        ctx["vision"] = {
            "estado":       "sin_camara",
            "nota":         "No hay imagen disponible. Basar diagnóstico en la descripción textual del campo 'pregunta'.",
            "health_category":  "desconocido",
            "disease_detected": "no evaluado",
            "severity_index":   None,
        }

    elif modo == "riego_fertilizacion":
        ctx["suelo"] = _normalizar_suelo(suelo)

    elif modo == "economia":
        ctx["costos"] = costos or {}

    # ── Fragmentos RAG ────────────────────────────────────────────────────────
    # Máximo 1 fragmento, truncado a 150 chars.
    # RAZÓN DEL LÍMITE:
    #   Con num_ctx=512 en Jetson 2 GB, el presupuesto total del prompt es
    #   ~400 tokens. La plantilla del modo ocupa ~120 tokens. El contexto
    #   JSON base ocupa ~60-80 tokens. 150 chars de RAG ≈ 37 tokens.
    #   Total: ~257 tokens → deja ~255 tokens para la respuesta (num_predict=80)
    #   y margen de KV-cache. Si se usan 250 chars el total sube a ~300 tokens.
    if rag_fragmentos:
        ctx["contexto_local_cr"] = [
            {
                "fuente": f.get("fuente", "desconocido"),
                "info":   f.get("texto", "")[:150],  # REDUCIDO de 250 a 150
            }
            for f in rag_fragmentos[:1]   # Máximo 1 fragmento
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

    NOTA: No advierte sobre visión faltante porque en esta versión
    es correcto y esperado no tener datos de visión.
    """
    advertencias = []

    if ctx.get("modo") not in MODOS_VALIDOS:
        advertencias.append(f"Modo inválido: {ctx.get('modo')}")

    if "cultivo" not in ctx:
        advertencias.append("Falta sección 'cultivo'.")

    if ctx.get("modo") == "economia" and not ctx.get("costos"):
        advertencias.append("Modo economía sin datos de costos.")

    total_chars = len(json.dumps(ctx, ensure_ascii=False))
    # Umbral reducido a 800 chars para Jetson 2 GB con num_ctx=512
    if total_chars > 800:
        advertencias.append(
            f"Contexto largo ({total_chars} chars > 800). "
            "Riesgo de superar num_ctx=512 en Jetson 2 GB. "
            "Reducir fragmentos RAG o datos de suelo."
        )

    return advertencias


# ── Helpers privados ──────────────────────────────────────────────────────────

def _normalizar_suelo(suelo: Optional[dict]) -> dict:
    """Retorna suelo con valores por defecto para campos faltantes."""
    defaults = {
        "humedad_pct": None,
        "ph":          None,
        "nitrogeno":   "desconocido",
        "fosforo":     "desconocido",
        "potasio":     "desconocido",
    }
    if suelo:
        defaults.update(suelo)
    return defaults


def _validar(modo: str, etapa: str) -> None:
    if modo not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo '{modo}' inválido. Válidos: {MODOS_VALIDOS}"
        )
    if etapa not in ETAPAS_VALIDAS:
        raise ValueError(
            f"Etapa '{etapa}' inválida. Válidas: {ETAPAS_VALIDAS}"
        )