"""
scripts/init_db.py
------------------
Inicializa la base de datos SQLite e inserta datos de muestra
para pruebas de historial y análisis económico.

Uso:
  python scripts/init_db.py
  python scripts/init_db.py --clean   # eliminar y recrear BD
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Eliminar BD existente antes de crear")
    args = parser.parse_args()

    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)

    db_path = Path(cfg["base_datos"]["path"])

    if args.clean and db_path.exists():
        db_path.unlink()
        print(f"✅ Base de datos eliminada: {db_path}")

    from modules.persistence import AgriDatabase
    db = AgriDatabase(str(db_path))

    # --- Datos de muestra: precios históricos ---
    conn = db._get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tb_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       DATE,
            mercado     TEXT,
            calidad     TEXT,
            precio_crc  REAL
        );

        INSERT OR IGNORE INTO tb_prices (fecha, mercado, calidad, precio_crc) VALUES
            ('2026-05-01', 'PIMA', 'primera', 390),
            ('2026-05-01', 'PIMA', 'segunda', 290),
            ('2026-05-01', 'PIMA', 'tercera', 185),
            ('2026-04-24', 'PIMA', 'primera', 370),
            ('2026-04-24', 'PIMA', 'segunda', 275),
            ('2026-04-17', 'PIMA', 'primera', 410),
            ('2026-04-17', 'PIMA', 'segunda', 300);

        CREATE TABLE IF NOT EXISTS tb_weather (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha               DATE,
            precipitacion_mm    REAL,
            temperatura_max_c   REAL,
            temperatura_min_c   REAL,
            humedad_rel_pct     REAL
        );

        INSERT OR IGNORE INTO tb_weather (fecha, precipitacion_mm, temperatura_max_c, temperatura_min_c, humedad_rel_pct) VALUES
            ('2026-05-13', 8.5, 18.0, 12.0, 82),
            ('2026-05-12', 12.0, 17.5, 11.5, 88),
            ('2026-05-11', 0.0, 20.0, 13.0, 72),
            ('2026-05-10', 5.5, 18.5, 12.5, 79),
            ('2026-05-09', 3.0, 19.0, 12.0, 75),
            ('2026-05-08', 18.0, 16.0, 10.5, 92),
            ('2026-05-07', 22.0, 15.5, 10.0, 95);
    """)
    conn.commit()

    print(f"✅ Base de datos inicializada: {db_path}")
    print("   Tablas creadas: tb_diagnostics, tb_irrigation, tb_economic, tb_llm_log, tb_prices, tb_weather")

    # Verificar
    tablas = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tablas:
        count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"   {t[0]:25s} → {count} registros")

    db.close()
    print("\n✅ Listo. Ejecuta: python main.py")


if __name__ == "__main__":
    main()
