"""
modules/persistence.py
----------------------
Módulo F5 — Persistencia.

Gestiona la base de datos SQLite local para almacenar:
  - Diagnósticos fitosanitarios.
  - Recomendaciones de riego.
  - Análisis económicos.
  - Log de llamadas al LLM (métricas).

No requiere servidor; SQLite está incluido en la biblioteca estándar de Python.
Compatible con Jetson Nano (microSD ext4).
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AgriDatabase:
    """Gestión de la base de datos SQLite de AGRI-EDGE-IA."""

    def __init__(self, db_path: str = "data/db/agri_edge.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Inicialización del esquema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tb_diagnostics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                etapa           TEXT,
                health_category TEXT,
                disease_detected TEXT,
                severity_index  REAL,
                vision_json     TEXT,
                suelo_json      TEXT,
                llm_report      TEXT,
                latency_s       REAL,
                tokens_entrada  INTEGER,
                tokens_salida   INTEGER
            );

            CREATE TABLE IF NOT EXISTS tb_irrigation (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                etapa           TEXT,
                humedad_pct     REAL,
                ph              REAL,
                frecuencia      TEXT,
                volumen_litros  REAL,
                llm_recomendacion TEXT
            );

            CREATE TABLE IF NOT EXISTS tb_economic (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                costo_total     REAL,
                rendimiento_kg  REAL,
                calidad         TEXT,
                precio_kg       REAL,
                margen          REAL,
                llm_analisis    TEXT
            );

            CREATE TABLE IF NOT EXISTS tb_llm_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                modo            TEXT,
                latency_s       REAL,
                tokens_entrada  INTEGER,
                tokens_salida   INTEGER,
                success         INTEGER,
                error           TEXT
            );
        """)
        conn.commit()
        logger.debug("Base de datos inicializada en: %s", self.db_path)

    # ------------------------------------------------------------------
    # Diagnósticos
    # ------------------------------------------------------------------

    def guardar_diagnostico(self, etapa: str, vision: dict, suelo: dict,
                             llm_result: dict) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO tb_diagnostics
               (etapa, health_category, disease_detected, severity_index,
                vision_json, suelo_json, llm_report, latency_s, tokens_entrada, tokens_salida)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                etapa,
                vision.get("health_category"),
                vision.get("disease_detected"),
                vision.get("severity_index"),
                json.dumps(vision, ensure_ascii=False),
                json.dumps(suelo, ensure_ascii=False),
                llm_result.get("response", ""),
                llm_result.get("latency_s"),
                llm_result.get("prompt_tokens"),
                llm_result.get("response_tokens"),
            ),
        )
        conn.commit()
        logger.info("Diagnóstico guardado (id=%d).", cur.lastrowid)
        return cur.lastrowid

    def obtener_diagnosticos(self, limite: int = 10) -> list:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM tb_diagnostics ORDER BY timestamp DESC LIMIT ?", (limite,)
        )
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Riego
    # ------------------------------------------------------------------

    def guardar_riego(self, etapa: str, suelo: dict, riego_calc: dict, llm_resp: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO tb_irrigation
               (etapa, humedad_pct, ph, frecuencia, volumen_litros, llm_recomendacion)
               VALUES (?,?,?,?,?,?)""",
            (
                etapa,
                suelo.get("humedad_pct"),
                suelo.get("ph"),
                riego_calc.get("frecuencia"),
                riego_calc.get("volumen_litros_por_planta"),
                llm_resp,
            ),
        )
        conn.commit()
        logger.info("Recomendación de riego guardada (id=%d).", cur.lastrowid)
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Análisis económico
    # ------------------------------------------------------------------

    def guardar_economia(self, economia: dict, llm_resp: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO tb_economic
               (costo_total, rendimiento_kg, calidad, precio_kg, margen, llm_analisis)
               VALUES (?,?,?,?,?,?)""",
            (
                economia.get("costo_total_crc"),
                economia.get("rendimiento_esperado_kg"),
                economia.get("calidad"),
                economia.get("precio_referencia_crc_kg"),
                economia.get("margen_estimado_crc"),
                llm_resp,
            ),
        )
        conn.commit()
        logger.info("Análisis económico guardado (id=%d).", cur.lastrowid)
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Log LLM
    # ------------------------------------------------------------------

    def log_llm(self, modo: str, llm_result: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO tb_llm_log
               (modo, latency_s, tokens_entrada, tokens_salida, success, error)
               VALUES (?,?,?,?,?,?)""",
            (
                modo,
                llm_result.get("latency_s"),
                llm_result.get("prompt_tokens"),
                llm_result.get("response_tokens"),
                1 if llm_result.get("success") else 0,
                llm_result.get("error"),
            ),
        )
        conn.commit()
