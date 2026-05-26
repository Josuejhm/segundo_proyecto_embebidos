# 🐋 Docker Container para Yocto-Qwen

Guía completa para compilar imágenes Yocto con soporte Qwen LLM usando Docker.

---

## 📋 Requisitos

### En tu Host
- **Docker**: 24.0+
- **Docker Compose**: 2.0+
- **Espacio en disco**: 200GB+ libre
- **RAM**: 32GB+ recomendado
- **CPU**: 8+ cores recomendado
- **SO**: Linux, macOS (M1/M2), Windows (WSL2)

### Verificar instalación
```bash
docker --version
docker-compose --version
```

---

## 🚀 Inicio Rápido (3 pasos)

### **1. Preparar el repositorio**

```bash
# Clonar el proyecto original (si no lo tienes)
git clone https://github.com/johan-carvajal-godinez/yocto-jetson-ollama
cd yocto-jetson-ollama

# O usa tu repo local adaptado a Qwen
cd /ruta/a/tu/repo
```

**Estructura esperada:**
```
yocto-jetson-ollama/
├── Dockerfile              ← AQUÍ
├── docker-compose.yml      ← AQUÍ
├── docker-entrypoint.sh    ← AQUÍ
├── meta-qwen/              (creado por migrate-to-qwen.sh)
├── conf/
├── scripts/
└── volumes/                (se crea automáticamente)
    ├── build/
    ├── dl/
    ├── sstate/
    └── output/
```

### **2. Construir la imagen Docker**

```bash
# Build de la imagen (primera vez: ~10-15 minutos)
docker-compose build --no-cache

# O con progreso más verboso
docker-compose build --progress=plain
```

**Output esperado:**
```
Building builder
Step 1/XX : FROM ubuntu:22.04
...
Successfully tagged yocto-qwen:latest
```

### **3. Iniciar el contenedor**

```bash
# Modo background
docker-compose up -d

# O modo foreground (ver logs en vivo)
docker-compose up
```

**Verificar que está corriendo:**
```bash
docker-compose ps
# STATUS debe ser "Up"

docker-compose logs builder
```

---

## 🔧 Setup Inicial del Build

**IMPORTANTE**: Solo hacer esto UNA VEZ después de crear el contenedor.

```bash
# Opción A: Automático (RECOMENDADO)
docker-compose exec builder /entrypoint.sh init

# Opción B: Manual paso a paso
docker-compose exec builder bash
# Luego dentro del contenedor:
/yocto/scripts/setup-yocto.sh
```

**¿Qué hace el setup?**
1. ✅ Crea directorios necesarios
2. ✅ Descarga capas Yocto (poky, meta-tegra, meta-openembedded, etc.)
3. ✅ Configura meta-qwen
4. ✅ Inicializa BitBake
5. ✅ Configura local.conf y bblayers.conf

**Tiempo estimado**: 15-20 minutos (dependiendo de conexión)

---

## 🛠️ Compilar la Imagen

### **Opción 1: Script Automático**

```bash
# Ejecutar build completo
docker-compose exec builder /yocto/scripts/build-image-qwen.sh

# Output:
# 🔨 Compilando imagen Yocto con Qwen...
# ⏳ Iniciando BitBake (esto puede tomar 6-12 horas)...
# [10 %] pkg_name ... (progreso)
# ✅ Build completado!
```

### **Opción 2: Manual (más control)**

```bash
# Entrar al contenedor
docker-compose exec builder bash

# Dentro del contenedor:
source /yocto/layers/poky/oe-init-build-env /yocto/build

# Build
bitbake jetson-nano-qwen-image

# Ver progreso en otra terminal
docker-compose exec builder tail -f /yocto/build/tmp/log.do_build
```

### **Tiempo de Build**

| Escenario | Tiempo |
|-----------|--------|
| Primer build completo | 6-12 horas |
| Con sstate-cache | ~30 minutos |
| Clean rebuild | 6-12 horas |
| Cambio menor | 1-3 horas |

---

## 📁 Directorios Importantes

### Dentro del Contenedor

```
/yocto/
├── repo/              # Tu repositorio (bind mount)
├── layers/            # Capas Yocto descargadas
│   ├── poky/
│   ├── meta-tegra/
│   ├── meta-openembedded/
│   ├── meta-clang/
│   ├── meta-virtualization/
│   └── meta-qwen/
├── build/             # Directorio de build
│   ├── conf/
│   │   ├── local.conf
│   │   └── bblayers.conf
│   └── tmp/           # Compilación temporal
│       ├── log.do_build
│       └── deploy/
├── dl/                # Descargas (cache)
├── sstate/            # Shared state (compilaciones previas)
└── scripts/
    ├── setup-yocto.sh
    └── build-image-qwen.sh
```

### En tu Host

```
yocto-jetson-ollama/
└── volumes/           # Sincronizado con /yocto en el contenedor
    ├── build/
    ├── dl/
    ├── sstate/
    └── output/        # Imágenes finales
```

---

## 📊 Monitoreo del Build

### Ver logs en tiempo real

```bash
# Logs del contenedor
docker-compose logs -f builder

# Logs específicos de BitBake
docker-compose exec builder \
  tail -f /yocto/build/tmp/log.do_build

# Logs de tareas específicas
docker-compose exec builder \
  grep ERROR /yocto/build/tmp/log.do_build
```

### Estadísticas

```bash
# Uso de CPU/memoria
docker stats yocto-qwen-builder

# Espacio en disco
docker-compose exec builder \
  df -h /yocto

# Tamaño de downloads
du -sh /yocto/dl

# Tamaño de cache
du -sh /yocto/sstate
```

---

## ✅ Verificar Build Exitoso

Una vez completado, deberías ver:

```bash
# Entrar al contenedor
docker-compose exec builder bash

# Ver imagen generada
ls -lh /yocto/build/tmp/deploy/images/jetson-nano-devkit/

# Output esperado:
# jetson-nano-qwen-image-jetson-nano-devkit.tar.gz
# jetson-nano-qwen-image-jetson-nano-devkit.tegraflash.tar.gz
# other files...

# Extraer la imagen del contenedor al host
cp /yocto/build/tmp/deploy/images/jetson-nano-devkit/*.tar.gz \
   /yocto/output/
```

---

## 🔄 Reconstrucciones Rápidas

### Si solo cambias meta-qwen

```bash
# Copiar cambios al contenedor
docker-compose cp /ruta/local/meta-qwen builder:/yocto/layers/

# Rebuild (rápido, ~30 min)
docker-compose exec builder bash
source /yocto/layers/poky/oe-init-build-env /yocto/build
bitbake jetson-nano-qwen-image
```

### Limpiar build anterior

```bash
# Limpiar receta específica
docker-compose exec builder bash
source /yocto/layers/poky/oe-init-build-env /yocto/build
bitbake -c cleansstate jetson-nano-qwen-image
bitbake jetson-nano-qwen-image

# O limpiar TODO
rm -rf /yocto/build/tmp
```

---

## 🆘 Troubleshooting

### Error: "Disk space is full"

```bash
# Verificar espacio
docker-compose exec builder df -h /yocto

# Limpiar descargas antiguas
docker-compose exec builder \
  find /yocto/dl -type f -mtime +30 -delete

# Limpiar builds fallidos
docker-compose exec builder \
  rm -rf /yocto/build/tmp
```

### Error: "License agreement not accepted"

```bash
# Dentro del contenedor
docker-compose exec builder bash

# Editar local.conf
nano /yocto/build/conf/local.conf

# Agregar:
# LICENSE_FLAGS_ACCEPTED = "nvidia-tegra"

# Guardar y reintentear build
```

### Error: "Recipe meta-qwen not found"

```bash
# Verificar estructura
docker-compose exec builder \
  find /yocto/layers/meta-qwen -type f

# Debería tener:
# - conf/layer.conf
# - recipes-ai/qwen/qwen-service_1.0.bb
# - recipes-ai/qwen/files/qwen.service
# - recipes-images/jetson-nano-qwen-image.bb
```

### El build se congela

```bash
# Detener gracefully
docker-compose stop --time=30

# Si no, matar
docker-compose kill builder

# Ver qué quedó en proceso
docker-compose exec builder ps aux | grep bitbake

# Limpiar locks
docker-compose exec builder \
  find /yocto/build/tmp -name "*.lock" -delete
```

---

## 🧹 Limpieza y Mantenimiento

### Parar el contenedor (sin perder datos)

```bash
docker-compose stop
# Datos persisten en volumes/
```

### Remover contenedor e imagen

```bash
docker-compose down

# También eliminar imágenes
docker-compose down --rmi all

# También limpiar volúmenes (⚠️ ELIMINA DATOS)
docker-compose down -v
```

### Limpiar cache de Docker

```bash
# Remover imágenes sin usar
docker image prune -a

# Remover volúmenes sin usar
docker volume prune

# Todo
docker system prune -a --volumes
```

---

## 🔐 Seguridad (Para sistemas en producción)

### Limitar recursos

En `docker-compose.yml`, ajusta:

```yaml
deploy:
  resources:
    limits:
      cpus: '8'        # Max 8 cores
      memory: 32G      # Max 32GB RAM
```

### Network isolation

```bash
# No exponer SSH públicamente
# Remover o comentar EXPOSE 22

# Usar solo red interna
docker-compose exec builder bash  # Acceso seguro
```

### Volúmenes read-only

Para proteger código fuente:

```yaml
volumes:
  - .:/yocto/repo:ro  # Read-only
```

---

## 📈 Optimizaciones para Builds Rápidos

### Paralelización

En local.conf dentro del contenedor:

```bash
# Máximo de tu host
BB_NUMBER_THREADS = "16"
PARALLEL_MAKE = "-j 16"

# En docker-compose.yml
environment:
  BB_NUMBER_THREADS: 16
```

### Hash Equivalence Server

```bash
# En local.conf
BB_HASHSERVE = "auto"
BB_HASHSERVE_UPSTREAM = ""
```

Esto reutiliza builds previos más agresivamente.

### RAM disk para temporales

```bash
# Crear RAM disk en host
mkdir -p /mnt/ramdisk
mount -t tmpfs -o size=60g tmpfs /mnt/ramdisk

# En docker-compose.yml
volumes:
  - /mnt/ramdisk:/yocto/build/tmp  # Temporal en RAM
```

---

## 📚 Archivos en este Setup

```
Dockerfile
├─ Ubuntu 22.04
├─ Herramientas Yocto
├─ Git, Python3, pip
└─ Usuario 'builder'

docker-compose.yml
├─ Configuración de recursos
├─ Volúmenes persistentes
├─ Variables de entorno
└─ Network

docker-entrypoint.sh
├─ Setup automático
├─ Descarga de capas
├─ Configuración BitBake
└─ Scripts de build

meta-qwen/
├─ Receta Qwen LLM
├─ Servicio systemd
└─ Imagen Yocto

```

---

## 🎯 Flujo Completo (Paso a Paso)

```bash
# 1. Preparar repo
git clone <tu-repo>
cd <tu-repo>

# 2. Copiar archivos Docker
cp Dockerfile docker-compose.yml docker-entrypoint.sh .

# 3. Build de imagen Docker
docker-compose build --no-cache

# 4. Crear contenedor
docker-compose up -d

# 5. Setup inicial (solo primera vez)
docker-compose exec builder /entrypoint.sh init
# Esperar 15-20 minutos

# 6. Compilar imagen Yocto
docker-compose exec builder /yocto/scripts/build-image-qwen.sh
# Esperar 6-12 horas ☕

# 7. Verificar resultado
docker-compose exec builder \
  ls -lh /yocto/build/tmp/deploy/images/jetson-nano-devkit/

# 8. Extraer imagen al host
docker-compose cp \
  builder:/yocto/build/tmp/deploy/images/jetson-nano-devkit/*.tar.gz \
  ./output/

# 9. Flash a Jetson Nano
# (Ver documentación YOCTO_QWEN_ADAPTACION.md)
```

---

## 📞 Ayuda

Si encuentras problemas:

1. Ver logs: `docker-compose logs builder`
2. Ejecutar setup nuevamente: `docker-compose exec builder /entrypoint.sh init`
3. Revisar documentación: `YOCTO_QWEN_ADAPTACION.md`
4. Aumentar recursos disponibles en el host

---

**¡Listo! Ahora puedes compilar tu imagen Yocto con Qwen en un contenedor Docker aislado y reproducible!** 🚀
