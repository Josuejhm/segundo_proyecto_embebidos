#!/bin/bash
# =============================================================================
# docker-entrypoint.sh — AGRI-EDGE-IA Yocto Build
# =============================================================================
# CORRECCIONES vs versión anterior:
#   + local.conf con KERNEL_DEVICETREE, TEGRA_ROOTDEV, WKS_FILE, IMAGE_FSTYPES
#   + WKS file copiado a meta-tegra/wic/
#   + Receta con IMAGE_CLASSES += "image_types_tegra"
#   + Integración completa del proyecto AGRI-EDGE-IA
#   + Flash con .wic en lugar de dosdcard.sh
# =============================================================================

set -e

YOCTO_DIR="/yocto"
LAYERS_DIR="$YOCTO_DIR/layers"
BUILD_DIR="$YOCTO_DIR/build"
APP_REPO="https://github.com/Josuejhm/segundo_proyecto_embebidos.git"
APP_BRANCH="ModeloJetson"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ===========================================================================
# 1. CAPAS YOCTO
# ===========================================================================
download_yocto_layers() {
    info "Descargando capas Yocto (kirkstone)..."
    mkdir -p "$LAYERS_DIR"

    # Poky kirkstone
    if [ ! -d "$LAYERS_DIR/poky" ]; then
        info "Clonando poky kirkstone..."
        git clone --depth=1 -b kirkstone \
            https://git.yoctoproject.org/poky "$LAYERS_DIR/poky"
    fi

    # meta-openembedded kirkstone
    if [ ! -d "$LAYERS_DIR/meta-openembedded" ]; then
        info "Clonando meta-openembedded..."
        git clone --depth=1 -b kirkstone \
            https://github.com/openembedded/meta-openembedded "$LAYERS_DIR/meta-openembedded"
    fi

    # meta-tegra — RAMA CORRECTA para Jetson Nano (tegra210, L4T r32.7.x)
    # IMPORTANTE: kirkstone-l4t-r35.x NO existe para tegra210
    if [ ! -d "$LAYERS_DIR/meta-tegra" ]; then
        info "Clonando meta-tegra (kirkstone-l4t-r32.7.x)..."
        git clone --depth=1 -b kirkstone-l4t-r32.7.x \
            https://github.com/OE4T/meta-tegra "$LAYERS_DIR/meta-tegra"
    fi

    # meta-clang kirkstone
    if [ ! -d "$LAYERS_DIR/meta-clang" ]; then
        info "Clonando meta-clang..."
        git clone --depth=1 -b kirkstone \
            https://github.com/kraj/meta-clang "$LAYERS_DIR/meta-clang"
    fi

    success "Capas descargadas"
}

# ===========================================================================
# 2. WKS FILE — necesario para imagen .wic bootable
# ===========================================================================
setup_wks_file() {
    info "Configurando WKS file para SD card boot..."

    WKS_DIR="$LAYERS_DIR/meta-tegra/wic"
    mkdir -p "$WKS_DIR"

    # Verificar si meta-tegra ya tiene uno para Jetson Nano
    if ls "$WKS_DIR"/*jetson*nano* 2>/dev/null | grep -q ".wks"; then
        WKS_EXISTING=$(ls "$WKS_DIR"/*jetson*nano*.wks* 2>/dev/null | head -1)
        info "WKS existente en meta-tegra: $WKS_EXISTING"
        # Crear un symlink o copiar con nuestro nombre
    fi

    # Siempre crear el nuestro (nombre específico que referenciamos en local.conf)
    cat > "$WKS_DIR/jetson-nano-sd-card.wks.in" << 'WKSEOF'
part /boot --source bootimg-partition \
           --ondisk mmcblk1 \
           --fstype=vfat \
           --label boot \
           --active \
           --align 4096 \
           --fixed-size 512M

part / --source rootfs \
       --ondisk mmcblk1 \
       --fstype=ext4 \
       --label rootfs \
       --align 4096 \
       --extra-space 4096M
WKSEOF

    success "WKS file creado en $WKS_DIR/jetson-nano-sd-card.wks.in"
}

# ===========================================================================
# 3. CLONAR APLICACIÓN (AGRI-EDGE-IA) en el directorio de build
# Para que ROOTFS_POSTPROCESS_COMMAND la encuentre
# ===========================================================================
setup_app_sources() {
    APP_DIR="$LAYERS_DIR/../agri-edge-ia"

    if [ ! -d "$APP_DIR/.git" ]; then
        info "Clonando AGRI-EDGE-IA (rama $APP_BRANCH)..."
        git clone --depth=1 -b "$APP_BRANCH" "$APP_REPO" "$APP_DIR"
        success "Aplicación clonada en $APP_DIR"
    else
        info "Actualizando AGRI-EDGE-IA..."
        cd "$APP_DIR" && git pull origin "$APP_BRANCH" && cd -
        success "Aplicación actualizada"
    fi
}

# ===========================================================================
# 4. local.conf CORREGIDO
# ===========================================================================
configure_local_conf() {
    info "Configurando local.conf..."
    mkdir -p "$BUILD_DIR/conf"

    cat > "$BUILD_DIR/conf/local.conf" << 'EOF'
MACHINE = "jetson-nano-devkit"
DISTRO  = "poky"

# Kernel L4T r32.7.x (tegra210 / Jetson Nano)
PREFERRED_VERSION_linux-tegra = "4.9.%"

# DEVICE TREE — sin esto = FDT_ERR_BADMAGIC → Jetson colgado en logo NVIDIA
# A02 (1 CSI, la más común):
KERNEL_DEVICETREE = "tegra210-p3448-0000-p3449-0000-a02.dtb"
# B01 (2 CSI, 4GB RAM): descomenta y comenta la línea de arriba
# KERNEL_DEVICETREE = "tegra210-p3448-0002-p3449-0000-b00.dtb"

# SD card root — mmcblk1 = SD (no mmcblk0 que es eMMC interna)
TEGRA_ROOTDEV      = "mmcblk1p1"
TEGRA_FLASH_SDCARD = "1"

# Imagen .wic directamente flasheable con dd
WKS_FILE      = "jetson-nano-sd-card.wks.in"
IMAGE_FSTYPES += "wic wic.bz2 ext4"

LICENSE_FLAGS_ACCEPTED = "nvidia-tegra synaptics-killswitch"

SSTATE_DIR = "/yocto/sstate"
DL_DIR     = "/yocto/dl"

BB_NUMBER_THREADS = "8"
PARALLEL_MAKE     = "-j 8"

DISTRO_FEATURES_append = " systemd alsa pulseaudio pam"
VIRTUAL-RUNTIME_init_manager = "systemd"
VIRTUAL-RUNTIME_initscripts  = ""

# Tamaño grande para el stack ML (~15GB total)
IMAGE_ROOTFS_SIZE        = "10485760"
IMAGE_ROOTFS_EXTRA_SPACE = "5242880"

PACKAGE_CLASSES ?= "package_ipk"
BB_SIGNATURE_HANDLER = "OEBasicHash"
INHERIT += "buildstats"
EOF

    success "local.conf configurado"
}

# ===========================================================================
# 5. bblayers.conf
# ===========================================================================
configure_bblayers() {
    info "Configurando bblayers.conf..."

    cat > "$BUILD_DIR/conf/bblayers.conf" << EOF
POKY_BBLAYERS_CONF_VERSION = "2"
BBPATH = "\${TOPDIR}"
BBFILES ?= ""

BBLAYERS ?= " \\
  /yocto/layers/poky/meta \\
  /yocto/layers/poky/meta-poky \\
  /yocto/layers/poky/meta-yocto-bsp \\
  /yocto/layers/meta-openembedded/meta-oe \\
  /yocto/layers/meta-openembedded/meta-python \\
  /yocto/layers/meta-openembedded/meta-networking \\
  /yocto/layers/meta-openembedded/meta-multimedia \\
  /yocto/layers/meta-openembedded/meta-filesystems \\
  /yocto/layers/meta-tegra \\
  /yocto/layers/meta-clang \\
"
# meta-virtualization: comentado (requiere auth, no crítico)
EOF

    success "bblayers.conf configurado"
}

# ===========================================================================
# 6. RECETA — copiar a meta-poky
# ===========================================================================
create_image_recipe() {
    info "Instalando receta jetson-nano-qwen-image.bb en meta-poky..."

    RECIPE_DIR="$LAYERS_DIR/poky/meta-poky/recipes-core/images"
    mkdir -p "$RECIPE_DIR"

    # Copiar la receta completa (el archivo .bb está en el proyecto)
    cp /yocto/config/jetson-nano-qwen-image.bb "$RECIPE_DIR/" 2>/dev/null || {
        warn "Receta no encontrada en /yocto/config/, creando versión mínima..."
        create_minimal_recipe "$RECIPE_DIR"
    }

    success "Receta instalada en $RECIPE_DIR"
}

create_minimal_recipe() {
    local RECIPE_DIR="$1"

    cat > "$RECIPE_DIR/jetson-nano-qwen-image.bb" << 'BBEOF'
DESCRIPTION = "Jetson Nano — AGRI-EDGE-IA con Qwen2.5:3b"
LICENSE     = "MIT"

inherit core-image
IMAGE_CLASSES += "image_types_tegra"

IMAGE_FEATURES += "ssh-server-openssh package-management debug-tweaks"

IMAGE_INSTALL += " \
    packagegroup-core-boot \
    packagegroup-core-full-cmdline \
    python3 python3-pip python3-setuptools python3-numpy python3-requests \
    python3-pyyaml python3-dotenv python3-rich python3-pillow python3-scipy \
    opencv libopencv-core libopencv-imgproc libopencv-imgcodecs python3-opencv \
    alsa-utils alsa-lib espeak-ng espeak-ng-data portaudio-v19 \
    git curl wget nano htop tmux openssh openssh-sftp-server \
    net-tools iputils i2c-tools libgpiod libgpiod-tools python3-libgpiod \
    sqlite3 v4l-utils util-linux e2fsprogs-resize2fs \
    cuda-libraries tegra-libraries tegra-firmware tegra-udev-rules \
    systemd systemd-journald \
"

DISTRO_FEATURES_append = " systemd alsa pulseaudio pam"
VIRTUAL-RUNTIME_init_manager = "systemd"

IMAGE_LINGUAS            = "en-us"
IMAGE_ROOTFS_SIZE        = "10485760"
IMAGE_ROOTFS_EXTRA_SPACE = "5242880"

ROOTFS_POSTPROCESS_COMMAND += "setup_agri_dirs; install_agri_services; "

setup_agri_dirs() {
    install -d ${IMAGE_ROOTFS}/opt/agri-edge-ia
    install -d ${IMAGE_ROOTFS}/opt/agri-edge-ia/scripts
    install -d ${IMAGE_ROOTFS}/opt/models/ollama
    install -d ${IMAGE_ROOTFS}/var/log/agri-edge
    install -d ${IMAGE_ROOTFS}/var/lib/agri-edge/db
}

install_agri_services() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}/etc/systemd/system"
    install -d "$SYSTEMD_DIR/multi-user.target.wants"

    cat > "$SYSTEMD_DIR/agri-first-boot.service" << 'SVC'
[Unit]
Description=AGRI-EDGE-IA Setup Inicial
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/opt/agri-edge-ia/.setup_done

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/agri-edge-ia/scripts/first_boot.sh
StandardOutput=journal

[Install]
WantedBy=multi-user.target
SVC

    ln -sf ../agri-first-boot.service "$SYSTEMD_DIR/multi-user.target.wants/"

    cat > "${IMAGE_ROOTFS}/opt/agri-edge-ia/scripts/first_boot.sh" << 'FB'
#!/bin/bash
set -e
LOG="/var/log/agri-edge/first_boot.log"
mkdir -p /var/log/agri-edge
exec > >(tee -a "$LOG") 2>&1
echo "=== AGRI-EDGE-IA First Boot: $(date) ==="
echo "Clonando aplicación..."
cd /opt
[ -f agri-edge-ia/main.py ] || git clone --depth=1 -b ModeloJetson \
    https://github.com/Josuejhm/segundo_proyecto_embebidos.git agri-edge-ia
echo "Instalando pip deps..."
pip3 install --no-cache-dir sentence-transformers sounddevice onnxruntime tqdm
echo "Instalando Ollama..."
[ -f /usr/local/bin/ollama ] || {
    curl -L https://github.com/ollama/ollama/releases/download/v0.5.13/ollama-linux-arm64 \
        -o /usr/local/bin/ollama && chmod +x /usr/local/bin/ollama
}
echo "Iniciando Ollama y descargando Qwen2.5:3b..."
export OLLAMA_MODELS=/opt/models/ollama
/usr/local/bin/ollama serve &
sleep 10
/usr/local/bin/ollama pull qwen2.5:3b
touch /opt/agri-edge-ia/.setup_done
echo "=== Setup completado: $(date) ==="
FB
    chmod +x "${IMAGE_ROOTFS}/opt/agri-edge-ia/scripts/first_boot.sh"
}
BBEOF
}

# ===========================================================================
# 7. SCRIPT DE FLASH CORREGIDO
# ===========================================================================
create_flash_script() {
    info "Creando script de flash..."
    mkdir -p "$YOCTO_DIR/output"

    cat > "$YOCTO_DIR/output/flash_jetson.sh" << 'FLASHEOF'
#!/bin/bash
# =============================================================================
# flash_jetson.sh — Flash CORRECTO para Jetson Nano con imagen .wic
# =============================================================================
# YA NO usar dosdcard.sh (tenía el bug del DTB)
# La imagen .wic ya viene con el particionado correcto + DTB embebido
#
# Uso: sudo ./flash_jetson.sh /dev/sdX
# =============================================================================

set -e
DEVICE="$1"
DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

[ -z "$DEVICE" ] && {
    echo -e "${RED}ERROR:${NC} Especifica dispositivo: sudo ./flash_jetson.sh /dev/sdX"
    echo ""
    echo "Dispositivos disponibles:"
    lsblk -d -o NAME,SIZE,RM,MODEL 2>/dev/null | grep -E "^(sd|mm)"
    exit 1
}
[ "$EUID" -ne 0 ] && { echo "Ejecutar con sudo"; exit 1; }
[ ! -b "$DEVICE" ] && { echo "No existe: $DEVICE"; exit 1; }

# Buscar imagen .wic
WIC=$(ls "$DIR"/jetson-nano-qwen-image*.wic 2>/dev/null | grep -v bz2 | head -1)
WIC_BZ2=$(ls "$DIR"/jetson-nano-qwen-image*.wic.bz2 2>/dev/null | head -1)

[ -z "$WIC" ] && [ -z "$WIC_BZ2" ] && {
    echo -e "${RED}ERROR:${NC} No hay imagen .wic en $DIR"
    echo "Copia primero: cp /yocto/build/tmp/deploy/images/jetson-nano-devkit/*.wic* ."
    exit 1
}

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  FLASH AGRI-EDGE-IA → Jetson Nano   ${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "  Dispositivo: ${RED}$DEVICE${NC}"
echo -e "  Tamaño: $(lsblk -dno SIZE $DEVICE 2>/dev/null)"
[ -n "$WIC" ] && echo -e "  Imagen: $(basename $WIC)"
[ -n "$WIC_BZ2" ] && [ -z "$WIC" ] && echo -e "  Imagen: $(basename $WIC_BZ2) (comprimida)"
echo ""
echo "¿Confirmas? (escribe 'si')"
read -r CONFIRM
[ "$CONFIRM" != "si" ] && echo "Cancelado." && exit 0

# Desmontar
echo -e "${YELLOW}Desmontando...${NC}"
umount "${DEVICE}"* 2>/dev/null || true
sleep 1

# Limpiar inicio del disco
echo -e "${YELLOW}Limpiando tabla de particiones...${NC}"
dd if=/dev/zero of="$DEVICE" bs=1M count=10 conv=fsync 2>/dev/null
sync

# Flash
echo -e "${YELLOW}Flasheando imagen .wic...${NC}"
echo "(~20-35 minutos dependiendo de la microSD)"
echo ""

if [ -n "$WIC" ]; then
    dd if="$WIC" of="$DEVICE" bs=4M status=progress conv=fsync
elif [ -n "$WIC_BZ2" ]; then
    bzcat "$WIC_BZ2" | dd of="$DEVICE" bs=4M status=progress conv=fsync
fi

sync
echo ""
echo -e "${GREEN}✅ Flash completado${NC}"
echo ""
echo "Particiones resultantes:"
lsblk "$DEVICE"
echo ""

# Verificar que el DTB está en /boot
BOOT_PART="${DEVICE}1"
if [ -b "$BOOT_PART" ]; then
    TMP_MNT=$(mktemp -d)
    mount "$BOOT_PART" "$TMP_MNT" 2>/dev/null && {
        DTB=$(find "$TMP_MNT" -name "*.dtb" 2>/dev/null | head -1)
        if [ -n "$DTB" ]; then
            echo -e "${GREEN}✅ DTB encontrado: $(basename $DTB)${NC}"
        else
            echo -e "${RED}⚠️  No se encontró .dtb en /boot — revisar receta${NC}"
        fi
        umount "$TMP_MNT"
    }
    rm -rf "$TMP_MNT"
fi

echo ""
echo "Siguiente paso: inserta la microSD en el Jetson Nano y enciende."
echo "En el primer arranque, el sistema descargará Ollama y el modelo Qwen2.5:3b"
echo "(requiere conexión a internet en el primer boot, ~5-15 min)"
FLASHEOF

    chmod +x "$YOCTO_DIR/output/flash_jetson.sh"
    success "Script flash_jetson.sh creado"
}

# ===========================================================================
# ENTRYPOINT PRINCIPAL
# ===========================================================================
case "${1:-bash}" in
    init)
        info "=== SETUP YOCTO AGRI-EDGE-IA ==="
        download_yocto_layers
        setup_wks_file
        setup_app_sources
        configure_local_conf
        configure_bblayers
        create_image_recipe
        create_flash_script
        success "=== SETUP COMPLETADO ==="
        echo ""
        echo "Para compilar:"
        echo "  source /yocto/layers/poky/oe-init-build-env /yocto/build"
        echo "  bitbake jetson-nano-qwen-image"
        echo ""
        echo "Para flashear (después de compilar):"
        echo "  sudo /yocto/output/flash_jetson.sh /dev/sdX"
        ;;
    build)
        info "Compilando imagen..."
        source "$LAYERS_DIR/poky/oe-init-build-env" "$BUILD_DIR"
        bitbake jetson-nano-qwen-image
        # Copiar artefactos al output
        DEPLOY="$BUILD_DIR/tmp/deploy/images/jetson-nano-devkit"
        cp "$DEPLOY"/*.wic* "$YOCTO_DIR/output/" 2>/dev/null || true
        cp "$DEPLOY"/*.ext4 "$YOCTO_DIR/output/" 2>/dev/null || true
        cp "$DEPLOY"/*.manifest "$YOCTO_DIR/output/" 2>/dev/null || true
        success "Imagen en /yocto/output/"
        ls -lah /yocto/output/*.wic* 2>/dev/null || true
        ;;
    update-only)
        # Solo actualiza configs sin re-descargar capas
        info "Actualizando configuraciones..."
        setup_wks_file
        configure_local_conf
        configure_bblayers
        create_image_recipe
        success "Configuraciones actualizadas"
        ;;
    bash|*)
        exec /bin/bash
        ;;
esac
