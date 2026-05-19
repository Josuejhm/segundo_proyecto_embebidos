# AGRI-EDGE-IA

Sistema inteligente de borde para monitoreo y diagnóstico de cultivos de papa.
EdgeLLM sobre NVIDIA Jetson Nano B01 — TEC · CEDA · IS-2026

**Integrantes:**
- Leonardo Pérez Sandoval — Director del Proyecto
- David Leitón Flores — Líder Técnico / Arquitecto
- Josué Hernández Medina — Investigador / Auditor

**Facilitador:** Dr. Ing. Johan Carvajal Godínez — johcarvajal@itcr.ac.cr

---

## Estado actual del proyecto

| Fase | Descripción | Estado |
|---|---|---|
| Fase 0 | Validación LLM local | Completada |
| Fase 1 | Asistente CLI con mock de visión | Completada |
| Fase 2 | Modularización F1–F6 + tests | Completada |
| Fase 3A | RAG con documentos locales | Completada |
| Fase 3B | Visión OpenCV real | Pendiente |
| Fase 3C | Audio ASR/TTS | Pendiente |
| Fase 4 | Migración a Jetson Nano | Pendiente |
| Fase 5 | Imagen Yocto | Pendiente |

---

## Modelo LLM

**Modelo en uso:** `qwen2.5:3b`
Reemplazó a `phi3:mini` por menor tasa de alucinaciones y mejor salida JSON estructurada.

```bash
ollama pull qwen2.5:3b
```

---

## Instalación local

**Requisitos:** Python 3.9+, Ollama, Linux o WSL.

```bash
# 1. Clonar repositorio
git clone https://github.com/tu-usuario/agri-edge-ia.git
cd agri-edge-ia

# 2. Entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Dependencias
pip install -r requirements.txt
pip install chromadb sentence-transformers

# 4. Instalar y levantar Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
ollama pull qwen2.5:3b

# 5. Inicializar base de datos
python scripts/init_db.py

# 6. Construir índice RAG (una sola vez en PC)
python scripts/build_rag_index.py

# 7. Verificar
python scripts/test_ollama.py --model qwen2.5:3b
```

---

## Ejecución

```bash
python main.py
```

Opciones del menú:

- `[1]` Diagnóstico fitosanitario — pide etapa, suelo y escenario de visión
- `[2]` Riego y fertilización — pide etapa y datos de suelo
- `[3]` Análisis económico — pide costos y rendimiento esperado
- `[L]` Consulta libre — el agricultor escribe en lenguaje natural sin formularios

---

## Cómo se le brinda contexto al LLM

El LLM nunca recibe preguntas sueltas. Antes de cada llamada se construye un contexto JSON con tres fuentes:

```
Datos del usuario (suelo, etapa, costos)
        +
Resultado de visión (mock o OpenCV)
        +
RAG: fragmentos de documentos locales
        |
        v
context_builder.py --> contexto JSON compacto
        |
        v
prompt_builder.py  --> prompt especializado por modo
        |
        v
Ollama + qwen2.5:3b --> respuesta JSON + resumen
```

### Ejemplo de contexto JSON

```json
{
  "modo": "diagnostico_fitosanitario",
  "cultivo": {
    "tipo": "papa",
    "variedad": "La Floresta",
    "ubicacion": "Tierra Blanca de Cartago, Costa Rica",
    "etapa_fenologica": "vegetativo"
  },
  "suelo": {
    "humedad_pct": 42,
    "ph": 5.7,
    "nitrogeno": "medio",
    "fosforo": "bajo",
    "potasio": "medio"
  },
  "vision": {
    "health_category": "regular",
    "disease_detected": "posible tizón tardío",
    "severity_index": 0.42,
    "confidence": 0.78
  },
  "contexto_local_cr": [
    {
      "fuente": "enfermedades_papa_CR.txt",
      "info": "El tizón tardío causado por P. infestans puede devastar..."
    }
  ]
}
```

### Regla de implementación

```
Nunca llamar al LLM con texto libre desde main.py.
Toda llamada pasa por:
  1. context_builder.py  --> contexto JSON validado
  2. prompt_builder.py   --> prompt especializado por modo
  3. llm_client.py       --> POST a Ollama, retorna JSON + resumen
```

---

## RAG — Recuperación de contexto local

El RAG permite que el LLM responda con información específica de Costa Rica sin internet.
El índice se construye una vez en PC y se copia como archivo estático en la imagen Yocto.

**Documentos disponibles en `rag/documentos/`:**

| Archivo | Contenido |
|---|---|
| `enfermedades_papa_CR.txt` | Tizón tardío, fusariosis, virosis, Rhizoctonia |
| `riego_fertilizacion_papa_CR.txt` | Demanda hídrica FAO-24, pH, N/P/K por etapa |
| `economia_papa_CR.txt` | Precios PIMA, costos por hectárea, rentabilidad |
| `INFORME_COSTO_KG_PAPA_V2_MEJORADO.md` | Estudios reales Ecuador 2019 y Perú 2021 |
| `Manual_Cultivo_Papa_Costa_Rica_INTA.md` | Manual INTA Costa Rica |
| `Crecimiento_acumulacion_nutrimentos_papa_Elbe-UCR.md` | Nutrición mineral UCR |
| `Almacenamiento_Papa_Ecuador_CIP.md` | Métodos de almacenamiento CIP |

**Comandos:**

```bash
# Construir o reconstruir el índice (al agregar documentos nuevos)
python scripts/build_rag_index.py

# Verificar que el índice recupera bien
python scripts/build_rag_index.py --test
```

---

## Estructura del proyecto

```
agri-edge-ia/
├── main.py                          # Orquestador principal
├── requirements.txt
├── config/
│   └── settings.yaml               # Modelo, timeouts, RAG, entorno
├── modules/
│   ├── llm_client.py               # Cliente Ollama con streaming
│   ├── context_builder.py          # Construye contexto JSON + RAG
│   ├── prompt_builder.py           # Ensambla prompt final por modo
│   ├── rag_retriever.py            # Recupera fragmentos del índice local
│   ├── vision_mock.py              # Simula visión (Fase 0-2)
│   ├── agri_logic.py               # Reglas de negocio agrícolas
│   ├── persistence.py              # SQLite
│   └── cli.py                      # Interfaz de línea de comandos
├── prompts/
│   ├── diagnostico_fitosanitario.md
│   ├── riego_fertilizacion.md
│   ├── economia.md
│   └── consulta_libre.md
├── rag/
│   ├── documentos/                 # Fuentes de conocimiento (.txt y .md)
│   └── index/                      # Índice vectorial ChromaDB (no editar)
├── scripts/
│   ├── test_ollama.py              # Validación Fase 0
│   ├── benchmark_llm.py            # Métricas de rendimiento
│   ├── build_rag_index.py          # Construye índice RAG en PC
│   └── init_db.py                  # Inicializa SQLite con datos de muestra
├── data/
│   └── db/                         # Base de datos SQLite
├── tests/
│   ├── test_context_builder.py
│   └── test_agri_logic.py
└── yocto/
    ├── notes.md                    # Notas técnicas para imagen Yocto
    └── agri-edge.service           # Servicio systemd
```

---

## Configuración principal

`config/settings.yaml`:

```yaml
entorno: "local"       # cambiar a "jetson" en el dispositivo

ollama:
  model: "qwen2.5:3b"
  timeout: 120
  num_predict: 300
  temperature: 0.1
  stream: true

rag:
  habilitado: true
  index_path: "rag/index"
  n_resultados: 2
```

Al cambiar `entorno: "jetson"`, se aplican automáticamente `timeout: 120` y `num_predict: 200`.

---

## Pruebas

```bash
# Tests unitarios
pytest tests/ -v

# Validar Ollama
python scripts/test_ollama.py --model qwen2.5:3b

# Benchmark (latencia y tasa JSON válido)
python scripts/benchmark_llm.py --model qwen2.5:3b --show-response
```

---

## Migración a Jetson Nano

Antes de migrar, verificar en PC:

- `pytest tests/ -v` — 100 % pass
- `benchmark_llm.py` — JSON > 80 % y latencia < 60s en PC
- Los cuatro modos del menú responden correctamente

En Jetson, cambiar en `settings.yaml`:

```yaml
entorno: "jetson"
```

Checklist en Jetson:

```
[ ] ollama pull qwen2.5:3b ejecutado en Jetson
[ ] python scripts/test_ollama.py pasa
[ ] free -m muestra RAM libre > 400 MB durante operacion
[ ] Temperatura bajo carga < 80 C
[ ] Camara CSI detectada: ls /dev/video*
[ ] Sistema opera sin internet (desconectar Ethernet y probar)
[ ] rag/index/ copiado desde PC
```

---

## Preparación para Yocto

Ver `yocto/notes.md` para instrucciones completas.

Archivos que van en la imagen como estáticos (no se generan en Jetson):
- `rag/index/` — índice vectorial pre-construido en PC
- Modelo GGUF qwen2.5:3b — incluir en receta Bitbake como `SRC_URI = "file://..."`

Restricción crítica: CUDA 10.2 únicamente. CUDA 11.x es incompatible con Jetson Nano B01 / Tegra X1.

Facilitador: Dr. Ing. Johan Carvajal Godínez — TEC · CEDA · IS-2026
