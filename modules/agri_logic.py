"""
modules/agri_logic.py
---------------------
Módulo F4 — Lógica Agrícola.

Contiene las reglas de negocio del dominio: riego, fertilización,
fenología y análisis económico básico para cultivo de papa en Costa Rica.

Este módulo no llama al LLM. Prepara los datos estructurados que
context_builder usará para construir el contexto.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Etapas fenológicas del cultivo de papa (La Floresta, Cartago CR)
# ------------------------------------------------------------------

ETAPAS_DURACION_DIAS = {
    "emergencia":    14,
    "vegetativo":    35,
    "tuberizacion":  30,
    "maduracion":    21,
}

# Demanda hídrica por etapa (mm/día, basado en modelo FAO-24)
DEMANDA_HIDRICA_FAO24 = {
    "emergencia":   2.5,
    "vegetativo":   4.0,
    "tuberizacion": 5.5,
    "maduracion":   3.0,
}

# Rangos óptimos de pH para papa
PH_OPTIMO = (5.5, 6.5)

# Rangos de humedad de suelo óptima (%)
HUMEDAD_OPTIMA = (60, 80)

# Precios de referencia PIMA (₡/kg) — actualizar con datos reales
PRECIOS_REFERENCIA = {
    "primera": 380,
    "segunda": 280,
    "tercera": 180,
}


# ------------------------------------------------------------------
# Riego
# ------------------------------------------------------------------

def calcular_riego(humedad_pct: float, etapa: str, precipitacion_mm_semana: float = 0.0) -> dict:
    """
    Calcula recomendación de riego basada en humedad del suelo y etapa fenológica.

    Returns:
        Dict con frecuencia, volumen_litros_por_planta, urgencia y justificacion.
    """
    demanda_diaria = DEMANDA_HIDRICA_FAO24.get(etapa, 4.0)
    deficit_humedad = max(0, HUMEDAD_OPTIMA[0] - humedad_pct)
    precipitacion_diaria = precipitacion_mm_semana / 7

    # Ajuste por precipitación: 1 mm precipitación ≈ 1 L/m² ≈ reducción proporcional
    demanda_neta = max(0, demanda_diaria - precipitacion_diaria)

    # Volumen estimado por planta (espaciado típico 0.3 m × 0.9 m = 0.27 m²)
    area_planta_m2 = 0.27
    volumen_litros = round(demanda_neta * area_planta_m2 * 10, 2)  # mm→L/m² factor 10

    if humedad_pct < 40:
        frecuencia = "inmediato (hoy)"
        urgencia = "alta"
    elif humedad_pct < HUMEDAD_OPTIMA[0]:
        frecuencia = "en 1–2 días"
        urgencia = "media"
    else:
        frecuencia = "en 3–4 días"
        urgencia = "baja"

    return {
        "frecuencia": frecuencia,
        "volumen_litros_por_planta": volumen_litros,
        "urgencia": urgencia,
        "demanda_neta_mm_dia": round(demanda_neta, 2),
        "deficit_humedad_pct": round(deficit_humedad, 1),
        "justificacion": (
            f"Etapa {etapa}: demanda FAO-24 = {demanda_diaria} mm/día. "
            f"Precipitación reciente = {precipitacion_diaria:.1f} mm/día. "
            f"Demanda neta = {demanda_neta:.2f} mm/día."
        ),
    }


# ------------------------------------------------------------------
# Fertilización
# ------------------------------------------------------------------

def recomendar_fertilizacion(etapa: str, nitrogeno: str, fosforo: str, potasio: str) -> dict:
    """
    Genera recomendación de fertilización según etapa y estado de nutrientes.

    Niveles: alto | medio | bajo | desconocido
    """
    recomendaciones = []

    # Nitrógeno
    if nitrogeno == "bajo":
        if etapa in ("vegetativo",):
            recomendaciones.append("Aplicar urea (46-0-0) a 150 kg/ha en banda.")
        else:
            recomendaciones.append("Aplicar urea (46-0-0) a 80 kg/ha.")
    elif nitrogeno == "desconocido":
        recomendaciones.append("Realizar análisis de suelo para N antes de aplicar.")

    # Fósforo
    if fosforo == "bajo":
        recomendaciones.append("Aplicar superfosfato triple (0-46-0) a 100 kg/ha.")

    # Potasio (crítico en tuberización)
    if potasio == "bajo" and etapa == "tuberizacion":
        recomendaciones.append("Aplicar cloruro de potasio (0-0-60) a 150 kg/ha. Prioritario en tuberización.")
    elif potasio == "bajo":
        recomendaciones.append("Aplicar cloruro de potasio (0-0-60) a 100 kg/ha.")

    if not recomendaciones:
        recomendaciones.append("Niveles de nutrientes adecuados para esta etapa.")

    return {
        "etapa": etapa,
        "recomendaciones": recomendaciones,
        "advertencia": "Confirmar con análisis de suelo certificado antes de aplicar.",
    }


# ------------------------------------------------------------------
# Análisis económico básico
# ------------------------------------------------------------------

def analizar_economia(
    costo_total_crc: float,
    rendimiento_esperado_kg: float,
    calidad: str = "segunda",
    precio_override: Optional[float] = None,
) -> dict:
    """
    Calcula margen esperado y punto de equilibrio.

    Args:
        costo_total_crc: Costo total del ciclo en colones costarricenses.
        rendimiento_esperado_kg: Kilos esperados de cosecha.
        calidad: primera | segunda | tercera.
        precio_override: Si se provee, sobreescribe el precio de referencia PIMA.

    Returns:
        Dict con precio_crc_kg, ingresos_esperados, margen, punto_equilibrio_kg.
    """
    precio_kg = precio_override or PRECIOS_REFERENCIA.get(calidad, PRECIOS_REFERENCIA["segunda"])
    ingresos = round(precio_kg * rendimiento_esperado_kg, 0)
    margen = round(ingresos - costo_total_crc, 0)
    punto_equilibrio = round(costo_total_crc / precio_kg, 1) if precio_kg > 0 else 0

    return {
        "calidad": calidad,
        "precio_referencia_crc_kg": precio_kg,
        "rendimiento_esperado_kg": rendimiento_esperado_kg,
        "ingresos_esperados_crc": ingresos,
        "costo_total_crc": costo_total_crc,
        "margen_estimado_crc": margen,
        "punto_equilibrio_kg": punto_equilibrio,
        "rentable": margen > 0,
    }


# ------------------------------------------------------------------
# Utilidad
# ------------------------------------------------------------------

def estado_ph(ph: float) -> str:
    """Clasifica el pH del suelo para papa."""
    if ph < 4.5:
        return "muy_acido"
    elif ph < PH_OPTIMO[0]:
        return "acido"
    elif ph <= PH_OPTIMO[1]:
        return "optimo"
    elif ph <= 7.5:
        return "ligeramente_alcalino"
    else:
        return "alcalino"
