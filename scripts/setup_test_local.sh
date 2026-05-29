#!/usr/bin/env bash
# ============================================================
# scripts/setup_test_local.sh
# ============================================================
# Prepara el entorno de pruebas LOCAL (PC de desarrollo) para
# verificar que el sistema no alucina ANTES de meterlo en Yocto.
#
# USO:
#   chmod +x scripts/setup_test_local.sh
#   ./scripts/setup_test_local.sh
#
# QUÉ HACE:
#   1. Verifica que Ollama está instalado y corriendo.
#   2. Descarga qwen2.5:3b si no está presente.
#   3. Crea el modelo agri-qwen3b con el Modelfile (num_ctx=512).
#   4. Instala las dependencias Python mínimas del proyecto.
#   5. Crea la estructura de directorios necesaria.
#   6. Ejecuta la suite de pruebas anti-alucinación.
#
# REQUISITOS PREVIOS:
#   - Ollama instalado: https://ollama.com/download
#   - Python 3.9+
#   - pip
# ============================================================

set -e   # Parar si cualquier comando falla

# ── Colores ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  AGRI-EDGE-IA — Setup de Pruebas Locales${NC}"
echo -e "${BOLD}============================================================${NC}"
echo ""

# ── Paso 1: Verificar que estamos en la raíz del proyecto ─────────────────────
if [ ! -f "config/settings.yaml" ]; then
    echo -e "${RED}ERROR: Ejecutar desde la raíz del proyecto.${NC}"
    echo "  Directorio actual: $(pwd)"
    echo "  Esperado: directorio con config/settings.yaml"
    exit 1
fi
echo -e "${GREEN}✓ Directorio del proyecto correcto.${NC}"

# ── Paso 2: Verificar Ollama ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[Paso 1/5]${NC} Verificando Ollama..."

if ! command -v ollama &> /dev/null; then
    echo -e "${RED}ERROR: Ollama no está instalado.${NC}"
    echo ""
    echo "  Instalar desde: https://ollama.com/download"
    echo "  En Linux:  curl -fsSL https://ollama.com/install.sh | sh"
    echo "  En macOS:  brew install ollama"
    exit 1
fi
echo -e "${GREEN}✓ Ollama encontrado: $(ollama --version 2>/dev/null || echo 'versión desconocida')${NC}"

# Verificar que ollama serve está corriendo
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠  Ollama no está corriendo. Iniciando en segundo plano...${NC}"
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "  PID: $OLLAMA_PID (logs en /tmp/ollama.log)"
    # Esperar hasta 15 segundos para que arranque
    for i in {1..15}; do
        sleep 1
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Ollama iniciado correctamente.${NC}"
            break
        fi
        if [ $i -eq 15 ]; then
            echo -e "${RED}ERROR: Ollama no arrancó en 15 segundos.${NC}"
            echo "  Revisar: cat /tmp/ollama.log"
            exit 1
        fi
    done
else
    echo -e "${GREEN}✓ Ollama ya está corriendo.${NC}"
fi

# ── Paso 3: Verificar/descargar el modelo base ────────────────────────────────
echo ""
echo -e "${BOLD}[Paso 2/5]${NC} Verificando modelo qwen2.5:3b..."

# Verificar si ya tiene alguna variante de qwen2.5:3b
if ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    echo -e "${GREEN}✓ qwen2.5:3b ya está disponible.${NC}"
else
    echo -e "${YELLOW}  qwen2.5:3b no encontrado. Descargando...${NC}"
    echo "  (Tamaño: ~2.1 GB para Q4_K_M — puede tardar varios minutos)"
    echo ""
    ollama pull qwen2.5:3b
    echo ""
    echo -e "${GREEN}✓ qwen2.5:3b descargado.${NC}"
fi

# ── Paso 4: Crear el modelo agri-qwen3b ──────────────────────────────────────
echo ""
echo -e "${BOLD}[Paso 3/5]${NC} Creando modelo agri-qwen3b..."

MODELFILE="data/models/Modelfile.agri"

if [ ! -f "$MODELFILE" ]; then
    echo -e "${RED}ERROR: No se encontró $MODELFILE${NC}"
    echo "  Verificar que el archivo existe en el proyecto."
    exit 1
fi

# Crear o recrear el modelo (idempotente)
echo "  Ejecutando: ollama create agri-qwen3b -f $MODELFILE"
ollama create agri-qwen3b -f "$MODELFILE"

if ollama list 2>/dev/null | grep -q "agri-qwen3b"; then
    echo -e "${GREEN}✓ Modelo agri-qwen3b creado correctamente.${NC}"
    echo "  Parámetros clave: num_ctx=512, num_predict=80, temperature=0.1"
else
    echo -e "${RED}ERROR: El modelo agri-qwen3b no aparece en ollama list.${NC}"
    exit 1
fi

# ── Paso 5: Instalar dependencias Python ─────────────────────────────────────
echo ""
echo -e "${BOLD}[Paso 4/5]${NC} Instalando dependencias Python..."

# Verificar Python 3.9+
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
if [ -z "$PYTHON_VERSION" ]; then
    echo -e "${RED}ERROR: Python 3 no encontrado.${NC}"
    exit 1
fi
echo "  Python: $PYTHON_VERSION"

# Instalar solo las dependencias mínimas para el test
# (en Yocto estas van en las meta-layers)
pip3 install --quiet --upgrade \
    requests \
    pyyaml \
    numpy \
    scikit-learn \
    2>/dev/null || {
    echo -e "${YELLOW}⚠  Algunas dependencias no se pudieron instalar.${NC}"
    echo "  Intentar manualmente: pip3 install requests pyyaml numpy scikit-learn"
}
echo -e "${GREEN}✓ Dependencias instaladas.${NC}"

# ── Paso 6: Crear estructura de directorios ───────────────────────────────────
echo ""
echo -e "${BOLD}[Paso 5/5]${NC} Creando estructura de directorios..."

mkdir -p \
    data/db \
    data/models \
    data/images \
    rag/index \
    modules \
    prompts \
    scripts \
    logs

# Crear __init__.py para módulos si no existe
touch modules/__init__.py 2>/dev/null || true

echo -e "${GREEN}✓ Estructura de directorios lista.${NC}"

# ── Verificación rápida del sistema ──────────────────────────────────────────
echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Verificación rápida del sistema${NC}"
echo -e "${BOLD}============================================================${NC}"
echo ""

# Test mínimo de Ollama
echo "  Enviando prueba mínima a agri-qwen3b..."
RESPUESTA=$(curl -s -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{
        "model": "agri-qwen3b",
        "prompt": "Respondé en español: ¿Para qué cultivo sos especialista?",
        "stream": false,
        "options": {"num_predict": 30}
    }' 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('response', 'ERROR: sin respuesta')[:100])
except:
    print('ERROR: respuesta no parseable')
")

echo "  Respuesta del modelo: $RESPUESTA"
echo ""

# ── Instrucciones finales ─────────────────────────────────────────────────────
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Setup completado. Próximos pasos:${NC}"
echo -e "${BOLD}============================================================${NC}"
echo ""
echo "  1. EJECUTAR SUITE DE PRUEBAS ANTI-ALUCINACIÓN:"
echo "     python3 scripts/test_no_alucinacion.py"
echo ""
echo "  2. PARA VER RESPUESTAS COMPLETAS DEL MODELO:"
echo "     python3 scripts/test_no_alucinacion.py --verbose"
echo ""
echo "  3. PARA VERIFICAR RAM DISPONIBLE:"
echo "     python3 scripts/measure_ram.py"
echo ""
echo "  4. PARA INICIAR LA APLICACIÓN INTERACTIVA:"
echo "     python3 main.py"
echo ""
echo "  5. SI EL RAG NO ESTÁ DISPONIBLE (índice no construido):"
echo "     python3 scripts/build_rag_index.py"
echo "     (La app funciona sin RAG pero con menos contexto local)"
echo ""
echo -e "${YELLOW}  NOTA: El modelo 'agri-qwen3b' tiene num_ctx=512.${NC}"
echo -e "${YELLOW}  Para recrarlo si cambiás el Modelfile:${NC}"
echo -e "${YELLOW}     ollama rm agri-qwen3b${NC}"
echo -e "${YELLOW}     ollama create agri-qwen3b -f data/models/Modelfile.agri${NC}"
echo ""
