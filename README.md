# AGRI-EDGE-IA

**Sistema Inteligente de Borde para Monitoreo de Cultivos de Papa**
EdgeLLM sobre NVIDIA Jetson Nano B01 — TEC · CEDA · IS-2026

---

## Resumen Ejecutivo

AGRI-EDGE-IA es un asistente agrícola offline que corre sobre hardware embebido de bajo costo. Antes de construir la imagen Yocto o tocar el Jetson Nano, se desarrolla y valida primero en PC local porque:

1. Iterar sobre PC es decenas de veces más rápido que sobre Jetson.
2. Validar el LLM localmente elimina el riesgo de descubrir problemas de prompts en hardware restrictivo.
3. Python como orquestador permite pruebas unitarias rápidas de cada módulo de forma independiente.
4. El diseño modular (F1–F6) garantiza que reemplazar el mock de visión por OpenCV real no rompe nada.
5. Una vez que el asistente CLI funciona en PC, migrar a Jetson es básicamente un cambio de entorno, no de arquitectura.

La migración a Yocto ocurre al final, cuando el sistema ya es estable y probado.

---

## Arquitectura General

```
Entrada (Cámara / Micrófono / Teclado)
         ↓
  F1 — Captura y Preprocesamiento
         ↓
  F2 — Visión Computacional (mock → OpenCV + CUDA)
         ↓
  F4 — Lógica Agrícola (reglas de negocio locales)
         ↓
  context_builder.py → contexto JSON compacto
         ↓
  prompt_builder.py  → prompt especializado
         ↓
  F3 — LLM (Ollama + PHI-3-mini Q4_K_M)
         ↓
  F5 — Persistencia (SQLite)
         ↓
  F6 — Salida (CLI → Qt6 → Audio TTS)
```

---

## Flujo Local de Desarrollo

```
Fase 0 → Validar Ollama + modelo en PC
Fase 1 → Asistente CLI funcional (mock visión)
Fase 2 → Modularización F1–F6 + tests unitarios
Fase 3 → SQLite + logs + OpenCV real + audio
Fase 4 → Migración a Jetson Nano
Fase 5 → Empaquetado en imagen Yocto
```

---

## Cómo se le Brinda Contexto al LLM

Esta es la sección más importante del proyecto. El LLM **nunca** recibe preguntas sueltas.

### El problema

PHI-3-mini (u otro modelo pequeño) no conoce:
- El estado actual del cultivo.
- Los datos del suelo del agricultor.
- El resultado del análisis de visión.
- El historial de riegos o diagnósticos.
- Las condiciones locales de Costa Rica.

Si se le pregunta directamente "¿qué enfermedad tiene mi planta?", el modelo no puede responder con precisión porque no tiene esos datos.

### La solución: Contexto JSON estructurado

La aplicación construye un bloque JSON antes de cada llamada al LLM, con **solo los datos relevantes al modo activo** (para no desperdiciar tokens ni RAM).

### Flujo obligatorio

```
Datos del usuario + datos de cultivo + datos de suelo + resultado de visión
         ↓
  context_builder.py  →  dict de contexto validado
         ↓
  prompt_builder.py   →  prompt final con contexto inyectado
         ↓
  llm_client.py       →  POST /api/generate a Ollama
         ↓
  respuesta JSON + resumen corto
```

### Ejemplo de contexto JSON

```json
{
  "modo": "diagnostico_fitosanitario",
  "cultivo": {
    "tipo": "papa",
    "variedad": "La Floresta",
    "ubicacion": "Cartago, Costa Rica",
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
    "confidence": 0.78,
    "observations": [
      "manchas oscuras en hojas",
      "lesiones compatibles con daño foliar",
      "requiere validación en campo"
    ]
  },
  "restricciones_respuesta": {
    "idioma": "español costarricense claro",
    "formato": "json_mas_resumen",
    "max_tokens": 250,
    "incluir_nota_seguridad": true
  }
}
```

### Ejemplo de prompt final ensamblado

```
Eres un asistente agrícola offline para productores de papa en Costa Rica.
Trabajas sin conexión a internet. Usa ÚNICAMENTE el contexto JSON que se te proporciona.
No inventes datos que no estén en el contexto.
Responde en español costarricense claro y accesible.

[instrucciones de formato JSON...]

⚠️ Esta recomendación es orientativa. Consulte a un agrónomo certificado antes de aplicar agroquímicos.

CONTEXTO:
{...json aquí...}
```

### Regla de implementación

```
NUNCA llamar directamente a OllamaClient con texto libre desde main.py.
Toda llamada debe pasar por:
  1. context_builder.py  → genera el dict de contexto
  2. prompt_builder.py   → construye el prompt con build_llm_request()
  3. llm_client.py       → envía el prompt y retorna el resultado
```

### Checklist antes de enviar al LLM

- [ ] El contexto JSON es válido (parseable).
- [ ] El contexto no incluye datos innecesarios para el modo activo.
- [ ] El modo seleccionado coincide con la plantilla de prompt usada.
- [ ] `num_predict` está limitado (≤300 en PC, ≤200 en Jetson).
- [ ] La respuesta esperada está especificada como JSON.
- [ ] Se incluye nota de seguridad agronómica.
- [ ] La consulta se registra en SQLite (`tb_llm_log`).
- [ ] El contexto JSON tiene menos de 2000 caracteres.

---

## Instalación Local

### Requisitos

- Linux o WSL (Ubuntu 22.04+).
- Python 3.9+.
- Ollama instalado.

### Pasos

```bash
# 1. Clonar repositorio
git clone https://github.com/tu-usuario/agri-edge-ia.git
cd agri-edge-ia

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Instalar Ollama (si no está instalado)
curl -fsSL https://ollama.ai/install.sh | sh

# 5. Iniciar Ollama en background
ollama serve &

# 6. Descargar modelo objetivo
ollama pull phi3:mini

# Alternativa más liviana para pruebas iniciales:
# ollama pull tinyllama

# 7. Verificar modelo disponible
ollama list

# 8. Prueba manual desde terminal
ollama run phi3:mini "¿Cuál es la principal enfermedad del cultivo de papa?"

# 9. Inicializar base de datos
python scripts/init_db.py

# 10. Ejecutar validación Fase 0
python scripts/test_ollama.py --model phi3:mini
```

---

## Ejecución de Pruebas

```bash
# Validación de Ollama (Fase 0)
python scripts/test_ollama.py

# Benchmark de rendimiento
python scripts/benchmark_llm.py --runs 3

# Tests unitarios
pytest tests/ -v

# Test específico
pytest tests/test_agri_logic.py -v
```

---

## Ejecución del Asistente CLI

```bash
# Asegurarse que Ollama está corriendo
ollama serve &

# Iniciar asistente
python main.py
```

El asistente mostrará el menú, solicitará datos por teclado, construirá el contexto JSON, lo imprimirá antes de enviarlo, y mostrará la respuesta del LLM con métricas.

---

## Estructura del Proyecto

```
agri-edge-ia/
├── README.md                        # Este archivo
├── requirements.txt                 # Dependencias Python mínimas
├── main.py                          # Orquestador principal
├── config/
│   └── settings.yaml               # Configuración (host Ollama, modelo, BD)
├── prompts/
│   ├── diagnostico_fitosanitario.md # Plantilla de prompt para diagnóstico
│   ├── riego_fertilizacion.md       # Plantilla de prompt para riego
│   └── economia.md                  # Plantilla de prompt para economía
├── modules/
│   ├── llm_client.py               # F3: cliente HTTP para Ollama
│   ├── context_builder.py          # F3: construye el contexto JSON
│   ├── prompt_builder.py           # F3: ensambla prompt final
│   ├── vision_mock.py              # F2: simulación de visión (Fase 0-2)
│   ├── agri_logic.py               # F4: reglas de negocio agrícolas
│   ├── persistence.py              # F5: SQLite
│   └── cli.py                      # F6: interfaz de línea de comandos
├── scripts/
│   ├── test_ollama.py              # Validación Fase 0
│   ├── benchmark_llm.py            # Métricas de rendimiento
│   └── init_db.py                  # Inicialización de BD con datos muestra
├── data/
│   ├── images/                     # Imágenes de prueba (Fase 3+)
│   ├── db/                         # Base de datos SQLite
│   └── samples/                    # Datos de muestra para tests
├── tests/
│   ├── test_context_builder.py
│   ├── test_prompt_builder.py
│   └── test_agri_logic.py
└── yocto/
    ├── notes.md                    # Notas técnicas para imagen Yocto
    ├── agri-edge.service           # Servicio systemd
    └── recipe-draft/               # Borradores de recetas Bitbake
```

---

## Migración a Jetson Nano

### Checklist de migración (Fase 4)

- [ ] Ollama ARM64 build disponible y descargado.
- [ ] `ollama pull phi3:mini` ejecutado en Jetson (o modelo copiado desde PC).
- [ ] RAM libre verificada: `free -m` → disponible > 400 MB durante operación.
- [ ] `python scripts/test_ollama.py` pasa en Jetson.
- [ ] Latencia medida: `python scripts/benchmark_llm.py` → debe ser < 30s/consulta.
- [ ] `num_predict` reducido a 200 en `config/settings.yaml`.
- [ ] Cámara CSI detectada: `ls /dev/video*`.
- [ ] OpenCV con CUDA 10.2 compilado y probado.
- [ ] SQLite funciona en microSD ext4.
- [ ] Sistema opera completamente sin internet.
- [ ] Temperatura monitorizada durante carga: `cat /sys/devices/virtual/thermal/thermal_zone*/temp`.

### Ajustes para Jetson

```yaml
# config/settings.yaml — ajustes para Jetson Nano
ollama:
  timeout: 180        # más tiempo para GPU Maxwell
  num_predict: 200    # reducir tokens para presión de RAM
```

---

## Preparación para Yocto

Ver `yocto/notes.md` para instrucciones detalladas.

**Regla**: No construir imagen Yocto hasta que:
1. `pytest tests/ -v` → 100% pass.
2. `python scripts/benchmark_llm.py` → latencia < 30s en Jetson, JSON > 80%.
3. Los 3 casos de uso demuestran funcionamiento correcto en Jetson con datos reales.

---

## Criterios de Aceptación por Fase

### Fase 0 — Validación Local LLM

| Criterio | Valor mínimo |
|---|---|
| `test_ollama.py` 4/4 tests pasan | 100% |
| Latencia de inferencia en PC | < 60s |
| Respuesta coherente en español | Sí |

### Fase 1 — Asistente CLI

| Criterio | Valor mínimo |
|---|---|
| `main.py` genera recomendación agrícola | Sí |
| Contexto JSON impreso es válido | Siempre |
| LLM responde JSON parseable | ≥ 8/10 consultas |
| Prompt no supera 3000 caracteres | Siempre |
| Sin dependencias incompatibles con ARM64 | Sí |

### Fase 4 — Jetson Nano

| Criterio | Valor mínimo |
|---|---|
| RAM en operación normal | < 3.6 GB |
| Latencia respuesta LLM | < 30s |
| Temperatura bajo carga | < 80°C |
| Operación sin internet | Completa |

---

## Métricas Recomendadas

Las siguientes métricas se registran automáticamente en `tb_llm_log`:

| Métrica | Cómo medirla |
|---|---|
| Latencia total | `llm_result["latency_s"]` |
| Tokens de entrada | `llm_result["prompt_tokens"]` |
| Tokens de salida | `llm_result["response_tokens"]` |
| Tasa de éxito JSON | `json_ok / total_consultas` |
| Uso RAM | `/proc/meminfo → MemAvailable` |
| Errores LLM | `tb_llm_log WHERE success=0` |

Para ver métricas históricas:

```bash
sqlite3 data/db/agri_edge.db \
  "SELECT modo, AVG(latency_s), AVG(tokens_salida), 
   SUM(CASE WHEN success=1 THEN 1 ELSE 0 END)*100/COUNT(*) as pct_ok
   FROM tb_llm_log GROUP BY modo;"
```

---

## Limitaciones Actuales (Fase 0-1)

- Visión computacional es un mock; no analiza imágenes reales.
- No hay integración de audio (ASR/TTS).
- No hay interfaz gráfica Qt6.
- La base de datos de precios PIMA es estática (datos de muestra).
- Los modelos de enfermedades no están validados con datos de campo costarricense.

---

## Próximos Pasos Inmediatos

1. Ejecutar `python scripts/test_ollama.py` → confirmar Fase 0.
2. Ejecutar `python scripts/benchmark_llm.py` → medir latencia base.
3. Ejecutar `python main.py` → primera consulta de diagnóstico con mock.
4. Revisar el JSON que imprime antes de enviarlo al LLM.
5. Ajustar prompts en `prompts/` si la respuesta no es la esperada.
6. Correr `pytest tests/ -v` y asegurar 100% de tests pasando.
7. Iniciar Fase 3: reemplazar `vision_mock.py` por `vision_opencv.py`.

---

## Equipo

| Rol | Integrante |
|---|---|
| Director del Proyecto | Leonardo Pérez Sandoval |
| Líder Técnico / Arquitecto | David Leitón Flores |
| Investigador(a) / Auditor(a) | Josué Hernández Medina |

Facilitador: Dr. Ing. Johan Carvajal Godínez — TEC · CEDA · IS-2026
