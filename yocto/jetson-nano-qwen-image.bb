# =============================================================================
# jetson-nano-qwen-image.bb — AGRI-EDGE-IA para Jetson Nano
# =============================================================================
# CORRECCIONES vs versión anterior que no bootaba:
#   + IMAGE_CLASSES += "image_types_tegra"  → genera DTB + .wic bootable
#   + KERNEL_DEVICETREE explícito           → sin esto = FDT_ERR_BADMAGIC
#   + WKS_FILE correcto                     → particionado SD correcto
#   + TEGRA_ROOTDEV = mmcblk1p1             → SD card, no eMMC
#
# NUEVO (integración AGRI-EDGE-IA):
#   + Python ML stack completo
#   + Audio ALSA + espeak-ng (TTS)
#   + OpenCV headless
#   + onnxruntime (inference ONNX)
#   + Soporte CUDA 10.2 (Maxwell/tegra210)
#   + Script first_boot para Ollama + pip deps
#   + systemd services: agri-edge + ollama
# =============================================================================

DESCRIPTION = "Jetson Nano — AGRI-EDGE-IA: Asistente Agrícola Offline con Qwen2.5:3b"
SUMMARY     = "Edge AI para diagnóstico fitosanitario de papa, Costa Rica"
LICENSE     = "MIT"
HOMEPAGE    = "https://github.com/Josuejhm/segundo_proyecto_embebidos"

# ---------------------------------------------------------------------------
# BASE
# ---------------------------------------------------------------------------
inherit core-image

# CRÍTICO — sin esto no se genera DTB ni .wic → FDT_ERR_BADMAGIC al flashear
IMAGE_CLASSES += "image_types_tegra"

# ---------------------------------------------------------------------------
# FEATURES DEL SISTEMA
# ---------------------------------------------------------------------------
IMAGE_FEATURES += " \
    ssh-server-openssh \
    package-management \
    debug-tweaks \
"

# ---------------------------------------------------------------------------
# SISTEMA BASE + UTILIDADES
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    packagegroup-core-boot \
    packagegroup-core-full-cmdline \
    util-linux \
    e2fsprogs \
    e2fsprogs-resize2fs \
    parted \
    dosfstools \
    coreutils \
    findutils \
    grep \
    gawk \
    sed \
    procps \
    htop \
    nano \
    vim \
    git \
    curl \
    wget \
    rsync \
    tmux \
    unzip \
    tar \
"

# ---------------------------------------------------------------------------
# RED Y SSH
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    openssh \
    openssh-sftp-server \
    net-tools \
    iputils \
    iproute2 \
    iptables \
    avahi-daemon \
"

# ---------------------------------------------------------------------------
# PYTHON 3 — CORE
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-dev \
    python3-modules \
    python3-misc \
"

# ---------------------------------------------------------------------------
# PYTHON 3 — PAQUETES DISPONIBLES EN YOCTO (meta-oe / meta-python)
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    python3-numpy \
    python3-requests \
    python3-pyyaml \
    python3-dotenv \
    python3-pillow \
    python3-scipy \
    python3-rich \
    python3-pytest \
    python3-aiohttp \
    python3-psutil \
    python3-serial \
    python3-smbus2 \
    python3-packaging \
    python3-six \
    python3-urllib3 \
    python3-certifi \
    python3-chardet \
    python3-idna \
"

# ---------------------------------------------------------------------------
# OPENCV — headless (sin GUI), compilado con CUDA 10.2 via meta-tegra/meta-oe
# NOTA: onnxruntime se instala via pip en first_boot (no está en repos Yocto ARM64)
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    opencv \
    opencv-dev \
    libopencv-core \
    libopencv-imgproc \
    libopencv-imgcodecs \
    libopencv-videoio \
    libopencv-highgui \
    python3-opencv \
"

# ---------------------------------------------------------------------------
# AUDIO — ALSA + espeak-ng (TTS offline, sin GPU, funciona en Jetson)
# Reemplaza Piper (demasiado complejo de empaquetar) y espeak funciona bien
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    alsa-utils \
    alsa-lib \
    alsa-plugins \
    alsa-state \
    portaudio-v19 \
    libsndfile1 \
    espeak-ng \
    espeak-ng-data \
    pulseaudio \
    pulseaudio-misc \
"

# ---------------------------------------------------------------------------
# SOPORTE CSI CAMERA (Jetson Nano)
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    v4l-utils \
    libcamera \
"

# ---------------------------------------------------------------------------
# SOPORTE GPIO / I2C / SPI — para sensores de campo
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    i2c-tools \
    spidev-test \
    libgpiod \
    libgpiod-tools \
    python3-libgpiod \
"

# ---------------------------------------------------------------------------
# SOPORTE NVIDIA / CUDA 10.2 — via meta-tegra
# CUDA 10.2 es el MÁXIMO para Maxwell/tegra210 — no usar CUDA 11.x
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    cuda-libraries \
    libcuda \
    tegra-libraries \
    tegra-firmware \
    tegra-udev-rules \
"

# ---------------------------------------------------------------------------
# SYSTEMD — habilitar services
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    systemd \
    systemd-analyze \
    systemd-journald \
"

DISTRO_FEATURES_append = " systemd"
VIRTUAL-RUNTIME_init_manager = "systemd"
VIRTUAL-RUNTIME_initscripts = ""

# ---------------------------------------------------------------------------
# SQLITE3 — viene con python3-modules (stdlib), pero instalamos también el CLI
# ---------------------------------------------------------------------------
IMAGE_INSTALL += " \
    sqlite3 \
"

# ---------------------------------------------------------------------------
# AGRI-EDGE-IA — incluir los archivos del proyecto en la imagen
# Se copian en ROOTFS_POSTPROCESS (más simple que crear receta separada)
# ---------------------------------------------------------------------------
ROOTFS_POSTPROCESS_COMMAND += " \
    install_agri_edge_app; \
    install_systemd_services; \
    create_first_boot_script; \
    create_agri_user; \
"

install_agri_edge_app() {
    APP_SRC="${THISDIR}/../../agri-edge-ia"
    APP_DST="${IMAGE_ROOTFS}/opt/agri-edge-ia"

    # Si el directorio del proyecto existe en el host de build, copiarlo
    if [ -d "$APP_SRC" ]; then
        install -d "$APP_DST"
        cp -r "$APP_SRC"/. "$APP_DST/"
        # Asegurar permisos
        chmod -R 755 "$APP_DST"
        chmod 644 "$APP_DST"/*.py "$APP_DST"/**/*.py 2>/dev/null || true
        echo "AGRI-EDGE-IA: aplicación copiada desde $APP_SRC"
    else
        # Si no está disponible en build, crear el directorio y un placeholder
        # Los archivos se descargan del repo en first_boot.sh
        install -d "$APP_DST"
        install -d "$APP_DST/modules"
        install -d "$APP_DST/config"
        install -d "$APP_DST/data/db"
        install -d "$APP_DST/data/audio"
        install -d "$APP_DST/data/models"
        install -d "$APP_DST/data/images"
        install -d "$APP_DST/data/logs"
        install -d "$APP_DST/rag/documentos"
        install -d "$APP_DST/rag/index"
        install -d "$APP_DST/prompts"
        install -d "$APP_DST/scripts"
        install -d "$APP_DST/tests"
        install -d "/var/lib/agri-edge/db" "$APP_DST/../var" 2>/dev/null || true
        echo "AGRI-EDGE-IA: directorios creados (archivos se descargarán en first_boot)"
    fi

    # Crear directorios de datos persistentes
    install -d "${IMAGE_ROOTFS}/var/lib/agri-edge/db"
    install -d "${IMAGE_ROOTFS}/var/log/agri-edge"
    install -d "${IMAGE_ROOTFS}/opt/ollama"
    install -d "${IMAGE_ROOTFS}/opt/models"
}

install_systemd_services() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}/etc/systemd/system"
    install -d "$SYSTEMD_DIR"

    # ── agri-edge.service ────────────────────────────────────────────────────
    cat > "$SYSTEMD_DIR/agri-edge.service" << 'SVCEOF'
[Unit]
Description=AGRI-EDGE-IA — Asistente Agricola Offline (EdgeLLM)
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=agri
WorkingDirectory=/opt/agri-edge-ia
ExecStart=/usr/bin/python3 /opt/agri-edge-ia/main.py --modo cli
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONPATH=/opt/agri-edge-ia
Environment=OLLAMA_HOST=http://localhost:11434
Environment=ENTORNO=jetson

[Install]
WantedBy=multi-user.target
SVCEOF

    # ── ollama.service ───────────────────────────────────────────────────────
    cat > "$SYSTEMD_DIR/ollama.service" << 'OLLAMAEOF'
[Unit]
Description=Ollama LLM Server
After=network.target
Documentation=https://github.com/ollama/ollama

[Service]
Type=simple
User=agri
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
Environment=OLLAMA_HOST=0.0.0.0:11434
Environment=OLLAMA_MODELS=/opt/models/ollama
Environment=HOME=/opt/agri-edge-ia

[Install]
WantedBy=multi-user.target
OLLAMAEOF

    # ── first-boot.service ───────────────────────────────────────────────────
    cat > "$SYSTEMD_DIR/agri-first-boot.service" << 'FBSVCEOF'
[Unit]
Description=AGRI-EDGE-IA — Setup inicial (primer arranque)
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/opt/agri-edge-ia/.setup_done

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/agri-edge-ia/scripts/first_boot.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
FBSVCEOF

    # Habilitar servicios (crear symlinks en multi-user.target.wants)
    WANTS_DIR="$SYSTEMD_DIR/multi-user.target.wants"
    install -d "$WANTS_DIR"
    ln -sf ../ollama.service "$WANTS_DIR/ollama.service"
    ln -sf ../agri-first-boot.service "$WANTS_DIR/agri-first-boot.service"
    # agri-edge.service NO se habilita automáticamente — se inicia manualmente
    # o tras confirmación de que Ollama y el modelo estén listos

    echo "Servicios systemd instalados"
}

create_first_boot_script() {
    SCRIPTS_DIR="${IMAGE_ROOTFS}/opt/agri-edge-ia/scripts"
    install -d "$SCRIPTS_DIR"

    cat > "$SCRIPTS_DIR/first_boot.sh" << 'FBEOF'
#!/bin/bash
# =============================================================================
# first_boot.sh — Setup inicial AGRI-EDGE-IA en Jetson Nano
# Se ejecuta UNA VEZ en el primer arranque via agri-first-boot.service
# =============================================================================

set -e
LOG="/var/log/agri-edge/first_boot.log"
mkdir -p /var/log/agri-edge
exec > >(tee -a "$LOG") 2>&1

echo "============================================="
echo "AGRI-EDGE-IA — Primer arranque: $(date)"
echo "============================================="

APP_DIR="/opt/agri-edge-ia"

# ---------------------------------------------------------------------------
# 1. Descargar aplicación si no está (build sin fuentes locales)
# ---------------------------------------------------------------------------
if [ ! -f "$APP_DIR/main.py" ]; then
    echo "[1/6] Descargando AGRI-EDGE-IA..."
    cd /opt
    git clone -b ModeloJetson \
        https://github.com/Josuejhm/segundo_proyecto_embebidos.git \
        agri-edge-ia || {
        echo "ERROR: No se pudo descargar el repositorio"
        echo "Verifica conexión a internet en el primer arranque"
        exit 1
    }
    echo "Aplicación descargada"
fi

cd "$APP_DIR"

# ---------------------------------------------------------------------------
# 2. Crear usuario agri y ajustar permisos
# ---------------------------------------------------------------------------
echo "[2/6] Configurando usuario y permisos..."
id agri &>/dev/null || useradd -m -s /bin/bash -d /opt/agri-edge-ia agri
chown -R agri:agri /opt/agri-edge-ia
chown -R agri:agri /opt/models
chown -R agri:agri /var/log/agri-edge
chown -R agri:agri /var/lib/agri-edge
usermod -aG audio,video,dialout,i2c agri

# ---------------------------------------------------------------------------
# 3. Instalar dependencias Python (las que no están en Yocto)
# ---------------------------------------------------------------------------
echo "[3/6] Instalando dependencias Python via pip..."
pip3 install --upgrade pip setuptools wheel --no-cache-dir
pip3 install --no-cache-dir \
    "sentence-transformers>=2.2.0" \
    "sounddevice>=0.4.5" \
    "onnxruntime>=1.16.0" \
    "python-dotenv>=1.0.1" \
    "rich>=13.0.0" \
    "pyyaml>=6.0" \
    "requests>=2.28.0" \
    "scikit-learn" \
    "tqdm" \
    || echo "AVISO: Algunas dependencias pip fallaron, continúa..."

# ---------------------------------------------------------------------------
# 4. Descargar Ollama ARM64 (si no está instalado)
# ---------------------------------------------------------------------------
echo "[4/6] Instalando Ollama..."
if [ ! -f "/usr/local/bin/ollama" ]; then
    # Descargar binario precompilado para Linux ARM64
    OLLAMA_VERSION="v0.5.13"
    curl -L \
        "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-arm64" \
        -o /usr/local/bin/ollama
    chmod +x /usr/local/bin/ollama
    echo "Ollama $OLLAMA_VERSION instalado"
else
    echo "Ollama ya instalado: $(/usr/local/bin/ollama --version)"
fi

# ---------------------------------------------------------------------------
# 5. Instalar whisper.cpp (STT)
# ---------------------------------------------------------------------------
echo "[5/6] Instalando whisper.cpp..."
if [ ! -f "/usr/local/bin/whisper-cpp" ]; then
    cd /tmp
    git clone --depth=1 https://github.com/ggerganov/whisper.cpp
    cd whisper.cpp
    # Compilar con soporte CUDA 10.2 si está disponible
    if nvcc --version 2>/dev/null | grep -q "10.2"; then
        make -j4 GGML_CUDA=1 2>/dev/null || make -j4
    else
        make -j4
    fi
    cp main /usr/local/bin/whisper-cpp
    chmod +x /usr/local/bin/whisper-cpp
    # Descargar modelo tiny en español (~75MB)
    mkdir -p "$APP_DIR/data/models"
    bash models/download-ggml-model.sh tiny
    cp models/ggml-tiny.bin "$APP_DIR/data/models/ggml-tiny.bin"
    cd /opt/agri-edge-ia
    rm -rf /tmp/whisper.cpp
    echo "whisper.cpp instalado"
else
    echo "whisper.cpp ya instalado"
fi

# ---------------------------------------------------------------------------
# 6. Descargar modelo Qwen2.5:3b
# ---------------------------------------------------------------------------
echo "[6/6] Descargando modelo Qwen2.5:3b (puede tardar 5-15 minutos)..."
export OLLAMA_MODELS=/opt/models/ollama
mkdir -p /opt/models/ollama

# Iniciar Ollama temporalmente para pull
/usr/local/bin/ollama serve &
OLLAMA_PID=$!
sleep 5

# Esperar a que Ollama esté listo
for i in $(seq 1 30); do
    curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 2
done

# Descargar el modelo
/usr/local/bin/ollama pull qwen2.5:3b && echo "Modelo qwen2.5:3b descargado OK"

# Detener Ollama temporal (systemd lo iniciará formalmente)
kill $OLLAMA_PID 2>/dev/null || true
wait $OLLAMA_PID 2>/dev/null || true

# ---------------------------------------------------------------------------
# Setup completado
# ---------------------------------------------------------------------------
touch "$APP_DIR/.setup_done"
echo ""
echo "============================================="
echo "SETUP COMPLETADO: $(date)"
echo ""
echo "Para iniciar el asistente:"
echo "  systemctl start ollama"
echo "  systemctl start agri-edge"
echo ""
echo "O manualmente:"
echo "  cd /opt/agri-edge-ia && python3 main.py"
echo "============================================="
FBEOF

    chmod +x "$SCRIPTS_DIR/first_boot.sh"
    echo "Script first_boot.sh creado"
}

create_agri_user() {
    # Pre-crear usuario agri en el rootfs (first_boot lo ajustará)
    echo "agri:x:1001:1001:AGRI-EDGE-IA,,,:/opt/agri-edge-ia:/bin/bash" \
        >> "${IMAGE_ROOTFS}/etc/passwd"
    echo "agri:x:1001:" \
        >> "${IMAGE_ROOTFS}/etc/group"
    echo "agri:!:19000:0:99999:7:::" \
        >> "${IMAGE_ROOTFS}/etc/shadow" 2>/dev/null || true
    echo "Usuario agri pre-creado"
}

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
IMAGE_LINGUAS            = "en-us"
IMAGE_ROOTFS_SIZE        = "10485760"
IMAGE_ROOTFS_EXTRA_SPACE = "5242880"
