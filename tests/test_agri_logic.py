"""
tests/test_agri_logic.py
------------------------
Pruebas unitarias para modules/agri_logic.py

Uso:
  pytest tests/test_agri_logic.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.agri_logic import calcular_riego, recomendar_fertilizacion, analizar_economia, estado_ph


def test_riego_urgente_por_sequedad():
    resultado = calcular_riego(humedad_pct=30.0, etapa="vegetativo")
    assert resultado["urgencia"] == "alta"
    assert "inmediato" in resultado["frecuencia"]


def test_riego_baja_urgencia():
    resultado = calcular_riego(humedad_pct=75.0, etapa="vegetativo")
    assert resultado["urgencia"] == "baja"


def test_riego_tuberizacion_mayor_demanda():
    riego_veg = calcular_riego(humedad_pct=60.0, etapa="vegetativo")
    riego_tub = calcular_riego(humedad_pct=60.0, etapa="tuberizacion")
    assert riego_tub["volumen_litros_por_planta"] >= riego_veg["volumen_litros_por_planta"]


def test_fertilizacion_fosforo_bajo():
    resultado = recomendar_fertilizacion("vegetativo", "medio", "bajo", "medio")
    textos = " ".join(resultado["recomendaciones"])
    assert "fosforo" in textos.lower() or "fosfato" in textos.lower() or "superfosfato" in textos.lower()


def test_fertilizacion_potasio_tuberizacion():
    resultado = recomendar_fertilizacion("tuberizacion", "medio", "medio", "bajo")
    textos = " ".join(resultado["recomendaciones"])
    assert "potasio" in textos.lower() or "potásico" in textos.lower() or "cloruro" in textos.lower()


def test_economia_rentable():
    r = analizar_economia(costo_total_crc=300000, rendimiento_esperado_kg=3000, calidad="primera")
    assert r["rentable"] is True
    assert r["margen_estimado_crc"] > 0


def test_economia_no_rentable():
    r = analizar_economia(costo_total_crc=1500000, rendimiento_esperado_kg=1000, calidad="tercera")
    assert r["rentable"] is False
    assert r["margen_estimado_crc"] < 0


def test_ph_optimo():
    assert estado_ph(6.0) == "optimo"
    assert estado_ph(4.0) == "muy_acido"
    assert estado_ph(7.0) == "ligeramente_alcalino"
    assert estado_ph(8.0) == "alcalino"
