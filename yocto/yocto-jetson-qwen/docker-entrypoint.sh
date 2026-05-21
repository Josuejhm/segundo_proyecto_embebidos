#!/bin/bash

# docker-entrypoint.sh - Inicialización para contenedor Yocto-Qwen
# Simplificado: Solo lo esencial, sin dependencias de archivos que no existen
# Modelo: Qwen2.5:3b

set -e

YOCTO_DIR="/yocto"
LAYERS_DIR="${YOCTO_DIR}/layers"
BUILD_DIR="${YOCTO_DIR}/build"
DL_DIR="${YOCTO_DIR}/dl"
SSTATE_DIR="${YOCTO_DIR}/sstate"

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# ============================================
# FUNCIÓN: Descargar Capas Yocto
# ============================================

download_yocto_layers() {
    log_info "Descargando capas Yocto (10-15 minutos)..."
    
    cd "${LAYERS_DIR}"
    
    # Poky base
    if [ ! -d "poky" ]; then
        log_info "  → poky (kirkstone)..."
        git clone -b kirkstone --depth=1 https://git.yoctoproject.org/git/poky.git 2>/dev/null || \
        log_warn "    Ya existe o error de red (continuando...)"
    fi
    
    # meta-tegra (Jetson Nano)
    if [ ! -d "meta-tegra" ]; then
        log_info "  → meta-tegra (kirkstone-l4t-r35.4)..."
        git clone -b kirkstone-l4t-r35.4 --depth=1 https://github.com/OE4T/meta-tegra.git 2>/dev/null || \
        log_warn "    Ya existe o error de red (continuando...)"
    fi
    
    # meta-openembedded
    if [ ! -d "meta-openembedded" ]; then
        log_info "  → meta-openembedded (kirkstone)..."
        git clone -b kirkstone --depth=1 https://github.com/openembedded/meta-openembedded.git 2>/dev/null || \
        log_warn "    Ya existe o error de red (continuando...)"
    fi
    
    # meta-clang (LLVM)
    if [ ! -d "meta-clang" ]; then
        log_info "  → meta-clang (kirkstone)..."
        git clone -b kirkstone --depth=1 https://github.com/kraj/meta-clang.git 2>/dev/null || \
        log_warn "    Ya existe o error de red (continuando...)"
    fi
    
    # meta-virtualization
    if [ ! -d "meta-virtualization" ]; then
        log_info "  → meta-virtualization (kirkstone)..."
        git clone -b kirkstone --depth=1 https://github.com/openembedded/meta-virtualization.git 2>/dev/null || \
        log_warn "    Ya existe o error de red (continuando...)"
    fi
    
    log_success "Capas Yocto descargadas"
}

# ============================================
# FUNCIÓN: Crear meta-qwen si no existe
# ============================================

setup_meta_qwen() {
    log_info "Verificando meta-qwen..."
    
    if [ -d "${LAYERS_DIR}/meta-qwen" ]; then
        log_warn "meta-qwen ya existe. Saltando..."
        return
    fi
    
    log_info "Creando meta-qwen..."
    mkdir -p "${LAYERS_DIR}/meta-qwen"/{conf,recipes-ai/qwen/files,recipes-images}
    
    # Si existe en /yocto/repo (volume mount), copiar
    if [ -d "/yocto/repo/meta-qwen" ]; then
        log_info "  Copiando meta-qwen desde /yocto/repo..."
        cp -r /yocto/repo/meta-qwen/* "${LAYERS_DIR}/meta-qwen/" 2>/dev/null || true
    else
        # Crear estructura mínima
        cat > "${LAYERS_DIR}/meta-qwen/conf/layer.conf" << 'EOF'
BBPATH .= ":${LAYERDIR}"
BBFILES += "${LAYERDIR}/recipes-*/*/*.bb"
BBFILE_COLLECTIONS += "meta-qwen"
BBFILE_PATTERN_meta-qwen = "^${LAYERDIR}/"
LAYERVERSION_meta-qwen = "1"
LAYERSERIES_COMPAT_meta-qwen = "kirkstone"
LAYERDEPENDS_meta-qwen = "core openembedded-layer"
EOF
        log_success "meta-qwen.conf creada (mínima)"
    fi
    
    log_success "meta-qwen configurado"
}

# ============================================
# FUNCIÓN: Inicializar BitBake
# ============================================

init_bitbake() {
    log_info "Inicializando BitBake..."
    
    if [ -f "${BUILD_DIR}/conf/local.conf" ]; then
        log_warn "BitBake ya inicializado. Saltando..."
        return
    fi
    
    cd "${YOCTO_DIR}"
    
    # Source oe-init-build-env
    if [ -f "${LAYERS_DIR}/poky/oe-init-build-env" ]; then
        source "${LAYERS_DIR}/poky/oe-init-build-env" "${BUILD_DIR}" > /dev/null 2>&1 || true
        log_success "BitBake inicializado"
    else
        log_error "poky/oe-init-build-env no encontrado"
        return 1
    fi
}

# ============================================
# FUNCIÓN: Configurar local.conf
# ============================================

configure_local_conf() {
    log_info "Configurando local.conf..."
    
    local conf="${BUILD_DIR}/conf/local.conf"
    
    if [ ! -f "$conf" ]; then
        log_error "local.conf no existe"
        return 1
    fi
    
    # Agregar configuraciones
    cat >> "$conf" << 'EOF'

# ============================================
# Yocto-Qwen Configuration
# ============================================

MACHINE = "jetson-nano-devkit"
DISTRO = "poky"

BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8"

SSTATE_DIR = "/yocto/sstate"
DL_DIR = "/yocto/dl"

BB_HASHSERVE = "auto"
BB_HASHSERVE_UPSTREAM = ""

LICENSE_FLAGS_ACCEPTED = "nvidia-tegra"

LAYERSERIES_CORENAMES = "kirkstone"

EOF
    
    log_success "local.conf configurado"
}

# ============================================
# FUNCIÓN: Configurar bblayers.conf
# ============================================

configure_bblayers() {
    log_info "Configurando bblayers.conf..."
    
    local bblayers="${BUILD_DIR}/conf/bblayers.conf"
    
    if [ ! -f "$bblayers" ]; then
        log_error "bblayers.conf no existe"
        return 1
    fi
    
    # Reescribir con las capas correctas
    cat > "$bblayers" << 'EOF'
LCONF_VERSION = "7"
BBPATH = "${TOPDIR}"

BBLAYERS ?= " \
  /yocto/layers/poky/meta \
  /yocto/layers/poky/meta-poky \
  /yocto/layers/poky/meta-yocto-bsp \
  /yocto/layers/meta-openembedded/meta-oe \
  /yocto/layers/meta-openembedded/meta-python \
  /yocto/layers/meta-openembedded/meta-networking \
  /yocto/layers/meta-openembedded/meta-multimedia \
  /yocto/layers/meta-tegra \
  /yocto/layers/meta-clang \
  /yocto/layers/meta-virtualization \
  /yocto/layers/meta-qwen \
  "
EOF
    
    log_success "bblayers.conf configurado"
}

# ============================================
# FUNCIÓN: Crear scripts de build
# ============================================

create_build_scripts() {
    log_info "Creando scripts de build..."
    
    mkdir -p "${YOCTO_DIR}/scripts"
    
    # Script: build-image-qwen.sh
    cat > "${YOCTO_DIR}/scripts/build-image-qwen.sh" << 'BUILDSCRIPT'
#!/bin/bash
set -e

BUILD_DIR="/yocto/build"
IMAGE_NAME="jetson-nano-qwen-image"

echo "🔨 Compilando imagen Yocto con Qwen2.5:3b..."
echo "   Imagen: $IMAGE_NAME"
echo "   Directorio: $BUILD_DIR"
echo ""

cd /yocto
source /yocto/layers/poky/oe-init-build-env "$BUILD_DIR"

echo "⏳ Iniciando BitBake (6-12 horas)..."
echo ""

if bitbake "$IMAGE_NAME"; then
    echo ""
    echo "✅ Build completado!"
    DEPLOY="/yocto/build/tmp/deploy/images/jetson-nano-devkit"
    if [ -d "$DEPLOY" ]; then
        echo "📦 Imágenes en: $DEPLOY"
        ls -lh "$DEPLOY"/*.tar.gz 2>/dev/null || echo "No .tar.gz found"
    fi
else
    echo ""
    echo "❌ Build falló"
    exit 1
fi
BUILDSCRIPT
    
    chmod +x "${YOCTO_DIR}/scripts/build-image-qwen.sh"
    log_success "Scripts de build creados"
}

# ============================================
# FUNCIÓN: Mostrar información
# ============================================

show_welcome() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║        🐋 Yocto-Qwen2.5:3b Build Container 🐋           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    echo "📍 Directorios:"
    echo "   Yocto:      /yocto"
    echo "   Capas:      /yocto/layers"
    echo "   Build:      /yocto/build"
    echo "   Descargas:  /yocto/dl"
    echo ""
    echo "🚀 Comandos:"
    echo "   docker-compose exec builder bash"
    echo "   /yocto/scripts/build-image-qwen.sh"
    echo ""
    echo "📚 Modelo: Qwen2.5:3b"
    echo ""
}

# ============================================
# MAIN
# ============================================

main() {
    case "${1:-}" in
        init)
            log_info "=== INICIALIZANDO CONTENEDOR ==="
            echo ""
            
            mkdir -p "${LAYERS_DIR}" "${BUILD_DIR}" "${DL_DIR}" "${SSTATE_DIR}"
            
            download_yocto_layers
            setup_meta_qwen
            init_bitbake
            configure_local_conf
            configure_bblayers
            create_build_scripts
            
            echo ""
            log_success "Inicialización completada"
            show_welcome
            
            exec bash
            ;;
        *)
            show_welcome
            exec "$@"
            ;;
    esac
}

main "$@"
