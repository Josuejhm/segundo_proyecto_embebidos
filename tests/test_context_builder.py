"""
tests/test_context_builder.py
-----------------------------
Pruebas unitarias para modules/context_builder.py

Uso:
  pytest tests/test_context_builder.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.context_builder import (
    build_context, validate_context, context_to_json, MODOS_VALIDOS
)


def test_build_contexto_diagnostico():
    ctx = build_context(
        modo="diagnostico_fitosanitario",
        etapa_fenologica="vegetativo",
        suelo={"humedad_pct": 50, "ph": 6.0},
        vision_result={"health_category": "regular", "disease_detected": "tizón tardío",
                       "severity_index": 0.42, "confidence": 0.78, "observations": []},
    )
    assert ctx["modo"] == "diagnostico_fitosanitario"
    assert ctx["cultivo"]["etapa_fenologica"] == "vegetativo"
    assert "vision" in ctx
    assert ctx["vision"]["severity_index"] == 0.42


def test_build_contexto_riego():
    ctx = build_context(
        modo="riego_fertilizacion",
        etapa_fenologica="tuberizacion",
        suelo={"humedad_pct": 35, "ph": 5.8},
    )
    assert "suelo" in ctx
    assert ctx["suelo"]["humedad_pct"] == 35


def test_build_contexto_economia():
    ctx = build_context(
        modo="economia",
        etapa_fenologica="maduracion",
        costos={"costo_total_crc": 400000, "rendimiento_esperado_kg": 3000},
    )
    assert "costos" in ctx
    assert ctx["costos"]["costo_total_crc"] == 400000


def test_modo_invalido():
    with pytest.raises(ValueError):
        build_context(modo="modo_inexistente", etapa_fenologica="vegetativo")


def test_etapa_invalida():
    with pytest.raises(ValueError):
        build_context(modo="diagnostico_fitosanitario", etapa_fenologica="florecimiento")


def test_validate_contexto_ok():
    ctx = build_context(
        modo="diagnostico_fitosanitario",
        etapa_fenologica="vegetativo",
        vision_result={"health_category": "bueno", "disease_detected": "ninguna",
                       "severity_index": 0.05, "confidence": 0.9, "observations": []},
    )
    advertencias = validate_context(ctx)
    assert advertencias == []


def test_json_compacto():
    ctx = build_context(modo="economia", etapa_fenologica="maduracion")
    json_str = context_to_json(ctx)
    import json
    parsed = json.loads(json_str)
    assert parsed["modo"] == "economia"
