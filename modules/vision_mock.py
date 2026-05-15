"""
modules/vision_mock.py
----------------------
Módulo F2 — Visión Computacional (fase mock).

En Fase 0 y 1, este módulo simula el resultado que producirá OpenCV
cuando se integre la cámara CSI real en el Jetson Nano.

Cuando se integre OpenCV real (Fase 3+), este módulo se reemplaza por
vision_opencv.py sin modificar ningún otro módulo del sistema.

La interfaz de salida es idéntica en ambos casos:
  -> dict con health_category, disease_detected, severity_index,
     confidence y observations.
"""

import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Catálogo de escenarios de prueba predefinidos
ESCENARIOS = {
    "sano": {
        "health_category": "excelente",
        "disease_detected": "ninguna",
        "severity_index": 0.02,
        "confidence": 0.95,
        "observations": [
            "follaje uniforme sin lesiones visibles",
            "coloración verde intensa normal",
            "no se detectan manchas o necrosis",
        ],
    },
    "tizon_leve": {
        "health_category": "regular",
        "disease_detected": "posible tizón tardío",
        "severity_index": 0.28,
        "confidence": 0.72,
        "observations": [
            "manchas oscuras incipientes en bordes de hojas",
            "patrón compatible con lesión foliar por P. infestans",
            "requiere validación en campo",
        ],
    },
    "tizon_grave": {
        "health_category": "crítico",
        "disease_detected": "tizón tardío confirmado",
        "severity_index": 0.81,
        "confidence": 0.88,
        "observations": [
            "lesiones necróticas extensas en más del 60 % del follaje",
            "esporulación visible en envés de hojas",
            "acción inmediata requerida",
        ],
    },
    "fusariosis": {
        "health_category": "malo",
        "disease_detected": "fusariosis (Fusarium solani)",
        "severity_index": 0.54,
        "confidence": 0.65,
        "observations": [
            "amarillamiento y marchitez basal",
            "posible pudrición en estolones",
            "se recomienda análisis de suelo",
        ],
    },
    "default": {
        "health_category": "regular",
        "disease_detected": "posible tizón tardío",
        "severity_index": 0.42,
        "confidence": 0.78,
        "observations": [
            "manchas oscuras en hojas",
            "patrón compatible con lesión foliar",
            "requiere validación en campo",
        ],
    },
}


def analyze(image_path: Optional[str] = None, escenario: Optional[str] = None) -> dict:
    """
    Simula el análisis de visión computacional.

    Args:
        image_path: Ruta a imagen local (ignorada en fase mock; se usará en Fase 3+).
        escenario: Nombre del escenario de prueba. Si es None, usa 'default'.
                   Opciones: sano | tizon_leve | tizon_grave | fusariosis | default | random

    Returns:
        Dict con resultado de visión compatible con context_builder.
    """
    if escenario == "random":
        key = random.choice(list(ESCENARIOS.keys()))
        logger.info("[VISION MOCK] Escenario aleatorio seleccionado: '%s'", key)
        resultado = dict(ESCENARIOS[key])
    elif escenario and escenario in ESCENARIOS:
        resultado = dict(ESCENARIOS[escenario])
        logger.info("[VISION MOCK] Escenario: '%s'", escenario)
    else:
        resultado = dict(ESCENARIOS["default"])
        logger.info("[VISION MOCK] Escenario por defecto.")

    if image_path:
        logger.info("[VISION MOCK] image_path ignorado en fase mock: %s", image_path)

    resultado["fuente"] = "mock"
    return resultado


def listar_escenarios() -> list[str]:
    """Retorna los nombres de escenarios disponibles."""
    return list(ESCENARIOS.keys()) + ["random"]
