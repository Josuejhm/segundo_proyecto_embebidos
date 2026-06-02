# Dockerfile para Yocto-Qwen2.5:3b (VERSIÓN FINAL CORREGIDA)
# NO intenta copiar directorios que no existen
# Paquetes correctos para Ubuntu 22.04

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Instalar dependencias (todo en un RUN para reducir capas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl wget sudo python3 python3-pip \
    python3-dev python3-venv chrpath cpio diffstat file lz4 texinfo zstd \
    gawk git-core unzip gcc gcc-multilib g++ \
    libsdl1.2-dev libxml-parser-perl xterm python3-distutils \
    libssl-dev repo htop vim nano less tree jq bc locales ca-certificates \
    openssh-client openssh-server \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Instalar kas (build reproducible)
RUN pip3 install --no-cache-dir kas

# Configurar locales
RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Crear usuario builder (no root)
RUN useradd -m -s /bin/bash -G sudo builder && \
    echo "builder ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Crear directorios (NOTA: No copiar nada, solo crear)
RUN mkdir -p /yocto/{build,dl,sstate,layers,scripts,output,repo} && \
    chown -R builder:builder /yocto /home/builder && \
    mkdir -p /home/builder/.ssh

# Configurar Git
RUN git config --global user.email "builder@yocto.local" && \
    git config --global user.name "Yocto Builder" && \
    git config --global safe.directory '*'

# Volúmenes y puertos
VOLUME ["/yocto/build", "/yocto/dl", "/yocto/sstate", "/yocto/output", "/yocto/repo"]
EXPOSE 22

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD test -d /yocto || exit 0

# Copiar entrypoint (cambiar a root temporalmente)
USER root
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown builder:builder /entrypoint.sh

# Cambiar a usuario builder
USER builder
WORKDIR /yocto

# Entrypoint y comando por defecto
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
