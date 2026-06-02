# AGRI-EDGE-IA — Notas Yocto Project

> Estas notas se preparan durante Fase 1-2 (local) para agilizar la migración en Fase 5.
> No construir la imagen Yocto hasta que el asistente local funcione correctamente.

## Meta-layers requeridos (en orden)

| Meta-layer          | Función                                              |
|---------------------|------------------------------------------------------|
| `meta` (Poky base)  | Capa base OpenEmbedded / Yocto Project               |
| `meta-poky`         | Distribución Poky y políticas de build               |
| `meta-openembedded` | OpenCV, libcamera, Python, herramientas del sistema  |
| **`meta-tegra`**    | **BSP CRÍTICO**: drivers Maxwell, kernel Tegra X1, CUDA 10.2, cuDNN, TensorRT, libcamera CSI |
| `meta-egl`          | Soporte EGL/GLES para Qt6 y aceleración OpenGL       |
| `meta-python`       | Python 3.9 y paquetes del ecosistema                 |
| `meta-qt6`          | Framework Qt6 para GUI táctil                        |
| `meta-agri-edge`    | **Capa custom**: recetas Ollama, PHI-3, app Python, systemd service |

## ⚠️ RESTRICCIÓN CRÍTICA: CUDA 10.2

- CUDA 10.2 es la versión MÁXIMA soportada por GPU Maxwell / JetPack 4.6.x.
- **NUNCA usar CUDA 11.x**: requiere JetPack 5.x, incompatible con Tegra X1.
- Verificar siempre con: `nvcc --version` → debe mostrar `release 10.2`.
- Toda receta de OpenCV y llama.cpp debe compilarse contra CUDA 10.2.

## Rutas de instalación en rootfs

```
/opt/agri-edge-ia/          → Aplicación Python
/opt/ollama/                → Runtime Ollama
/opt/models/phi3-mini/      → Modelo GGUF (PHI-3-mini Q4_K_M, ~2.0 GB)
/var/lib/agri-edge/db/      → Base de datos SQLite (persistente)
/var/log/agri-edge/         → Logs del sistema
/etc/systemd/system/        → agri-edge.service, ollama.service
```

## Estrategia para el modelo GGUF offline

El modelo PHI-3-mini Q4_K_M (~2.0 GB) NO puede descargarse durante el boot
porque el sistema opera sin internet. Estrategias:

1. **Incluir en rootfs (recomendado para prototipo):**
   Descargar el archivo `.gguf` en la PC de build y agregarlo como
   `SRC_URI = "file://phi3-mini-q4_k_m.gguf"` en la receta.

2. **MicroSD secundaria:**
   Modelo en partición separada montada en `/opt/models/`.

3. **Primera ejecución con internet (inicial):**
   Solo para carga inicial; después opera completamente offline.

## Checklist antes de construir imagen Yocto

- [ ] Asistente CLI funciona correctamente en PC local.
- [ ] Todos los tests unitarios pasan (`pytest tests/ -v`).
- [ ] Benchmark muestra latencia < 30s en prompt corto.
- [ ] Tasa JSON válido > 80%.
- [ ] Ollama ARM64 build verificado (descargar binario pre-compilado para ARM64).
- [ ] PHI-3-mini Q4_K_M confirmado en Jetson Nano con RAM < 3.6 GB.
- [ ] CUDA 10.2 verificado: `nvcc --version`.
- [ ] OpenCV compilado con CUDA 10.2 probado.
- [ ] Cámara CSI detectada: `ls /dev/video*`.
- [ ] SQLite funciona en microSD ext4.
- [ ] Servicio systemd arranca y reinicia correctamente.
- [ ] Sistema opera sin internet (desactivar Ethernet y probar).

## Tiempo estimado de compilación Yocto

- Primera compilación completa: **4–8 horas** (en PC con 8+ cores).
- Con sstate-cache: **30–90 minutos** en compilaciones incrementales.
- Habilitar sstate-cache desde el inicio para ahorrar tiempo.

## Receta base (borrador) — meta-agri-edge

```bitbake
SUMMARY = "AGRI-EDGE-IA — Asistente Agrícola EdgeLLM"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=..."

SRC_URI = "git://github.com/tu-usuario/agri-edge-ia.git;branch=main"

RDEPENDS_${PN} = "python3 python3-requests python3-yaml sqlite3 ollama"

do_install() {
    install -d ${D}/opt/agri-edge-ia
    cp -r ${S}/* ${D}/opt/agri-edge-ia/
    install -d ${D}/etc/systemd/system
    install -m 0644 ${S}/yocto/agri-edge.service ${D}/etc/systemd/system/
}

SYSTEMD_SERVICE_${PN} = "agri-edge.service"
inherit systemd
```
