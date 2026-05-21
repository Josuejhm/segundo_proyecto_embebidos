.PHONY: help build up down init logs shell build-image clean stop restart

# Variables
DOCKER_COMPOSE := docker-compose
BUILDER := $(DOCKER_COMPOSE) exec builder

# Colores
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Mostrar este mensaje de ayuda
	@echo "$(BLUE)╔════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║   Yocto-Qwen Docker Build System              ║$(NC)"
	@echo "$(BLUE)╚════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(GREEN)Comandos disponibles:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Ejemplos:$(NC)"
	@echo "  make build      # Construir imagen Docker"
	@echo "  make up         # Crear y iniciar contenedor"
	@echo "  make init       # Setup inicial de Yocto"
	@echo "  make build-image # Compilar imagen Yocto"
	@echo "  make shell      # Entrar al shell del contenedor"
	@echo ""

# ============================================
# Docker Container Management
# ============================================

build: ## Construir imagen Docker (primera vez)
	@echo "$(BLUE)🔨 Construyendo imagen Docker...$(NC)"
	$(DOCKER_COMPOSE) build --no-cache
	@echo "$(GREEN)✓ Imagen construida$(NC)"

build-cached: ## Construir imagen Docker (con cache)
	@echo "$(BLUE)🔨 Construyendo imagen Docker (con cache)...$(NC)"
	$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✓ Imagen construida$(NC)"

up: ## Crear y iniciar contenedor (background)
	@echo "$(BLUE)🚀 Iniciando contenedor...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Contenedor iniciado$(NC)"
	@echo "   Estado: $$($(DOCKER_COMPOSE) ps --format 'table {{.Status}}')"

up-fg: ## Iniciar contenedor en foreground (ver logs)
	@echo "$(BLUE)🚀 Iniciando contenedor (foreground)...$(NC)"
	$(DOCKER_COMPOSE) up

down: ## Detener y remover contenedor
	@echo "$(BLUE)⏹️ Deteniendo contenedor...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Contenedor detenido$(NC)"

stop: ## Parar contenedor (sin remover)
	@echo "$(BLUE)⏹️ Parando contenedor...$(NC)"
	$(DOCKER_COMPOSE) stop
	@echo "$(GREEN)✓ Contenedor parado$(NC)"

restart: ## Reiniciar contenedor
	@echo "$(BLUE)🔄 Reiniciando contenedor...$(NC)"
	$(DOCKER_COMPOSE) restart
	@echo "$(GREEN)✓ Contenedor reiniciado$(NC)"

logs: ## Ver logs en tiempo real
	$(DOCKER_COMPOSE) logs -f builder

logs-tail: ## Ver últimas 100 líneas de logs
	$(DOCKER_COMPOSE) logs --tail=100

ps: ## Ver estado del contenedor
	$(DOCKER_COMPOSE) ps

status: ## Ver estado detallado
	@echo "$(BLUE)Estado del contenedor:$(NC)"
	$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(BLUE)Uso de recursos:$(NC)"
	docker stats yocto-qwen-builder --no-stream || echo "Contenedor no está corriendo"

# ============================================
# Yocto Setup & Build
# ============================================

init: ## Ejecutar setup inicial de Yocto (SOLO PRIMERA VEZ)
	@echo "$(BLUE)⚙️ Configurando Yocto (primera ejecución)...$(NC)"
	@echo "$(YELLOW)⚠️  Esto descargará ~20GB de código. Espera 15-20 minutos...$(NC)"
	$(BUILDER) /entrypoint.sh init
	@echo "$(GREEN)✓ Setup completado$(NC)"

build-image: ## Compilar imagen Yocto (jetson-nano-qwen-image)
	@echo "$(BLUE)🔨 Compilando imagen Yocto...$(NC)"
	@echo "$(YELLOW)⚠️  Esto puede tomar 6-12 horas la primera vez...$(NC)"
	$(BUILDER) /yocto/scripts/build-image-qwen.sh

build-image-fast: ## Rebuild rápido (con cache)
	@echo "$(BLUE)⚡ Compilando imagen (rápido con cache)...$(NC)"
	$(BUILDER) bash -c "source /yocto/layers/poky/oe-init-build-env /yocto/build && bitbake jetson-nano-qwen-image"

clean-build: ## Limpiar build anterior
	@echo "$(YELLOW)🗑️ Limpiando build anterior...$(NC)"
	@echo "$(RED)⚠️  Esto eliminará toda la compilación anterior$(NC)"
	@read -p "¿Continuar? (y/N) " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(BUILDER) rm -rf /yocto/build/tmp; \
		echo "$(GREEN)✓ Build limpiado$(NC)"; \
	else \
		echo "Cancelado"; \
	fi

bitbake: ## Ejecutar bitbake con argumentos (ej: make bitbake ARGS="jetson-nano-qwen-image")
	@echo "$(BLUE)🔨 Ejecutando bitbake...$(NC)"
	$(BUILDER) bash -c "source /yocto/layers/poky/oe-init-build-env /yocto/build && bitbake $(ARGS)"

# ============================================
# Shell & Debugging
# ============================================

shell: ## Entrar a shell interactivo del contenedor
	@echo "$(BLUE)📟 Entrando al contenedor...$(NC)"
	$(DOCKER_COMPOSE) exec builder bash

root-shell: ## Entrar con permisos root
	@echo "$(BLUE)📟 Entrando al contenedor (root)...$(NC)"
	$(DOCKER_COMPOSE) exec -u root builder bash

build-logs: ## Ver logs de BitBake
	$(BUILDER) tail -f /yocto/build/tmp/log.do_build

bitbake-status: ## Ver estado actual de BitBake
	@echo "$(BLUE)BitBake tasks en progreso:$(NC)"
	$(BUILDER) ps aux | grep bitbake

# ============================================
# Información & Monitoring
# ============================================

info: ## Mostrar información del setup
	$(BUILDER) /entrypoint.sh info

space: ## Mostrar uso de espacio en disco
	@echo "$(BLUE)Espacio en disco:$(NC)"
	$(BUILDER) df -h /yocto
	@echo ""
	@echo "$(BLUE)Tamaño de directorios:$(NC)"
	$(BUILDER) du -sh /yocto/* 2>/dev/null | sort -h

resources: ## Ver recursos utilizados
	@echo "$(BLUE)Recursos del contenedor:$(NC)"
	docker stats yocto-qwen-builder --no-stream

list-artifacts: ## Listar artefactos generados
	@echo "$(BLUE)Imágenes generadas:$(NC)"
	@ls -lh volumes/output/*.tar.gz 2>/dev/null || echo "No hay imágenes generadas"
	@ls -lh volumes/output/*.tegraflash.tar.gz 2>/dev/null || echo ""

# ============================================
# Mantenimiento
# ============================================

prune: ## Limpiar contenedores, imágenes y volúmenes sin usar
	@echo "$(RED)⚠️  Esto eliminará datos que no se usan actualmente$(NC)"
	@read -p "¿Continuar? (y/N) " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(DOCKER_COMPOSE) down; \
		docker system prune -a --volumes; \
		echo "$(GREEN)✓ Limpieza completada$(NC)"; \
	else \
		echo "Cancelado"; \
	fi

clean-volumes: ## Limpiar volúmenes locales (CUIDADO: elimina datos)
	@echo "$(RED)⚠️  CUIDADO: Esto eliminará TODOS los datos de build$(NC)"
	@read -p "¿Continuar? (y/N) " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -rf volumes/; \
		echo "$(GREEN)✓ Volúmenes eliminados$(NC)"; \
	else \
		echo "Cancelado"; \
	fi

# ============================================
# Setup Rápido
# ============================================

full-setup: ## Setup completo: build → up → init
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@echo "$(GREEN)  Full Setup: Build + Up + Init$(NC)"
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@make build
	@make up
	@sleep 5
	@make init
	@echo ""
	@echo "$(GREEN)✓ Setup completeto!$(NC)"
	@echo "   Próximo paso: make build-image"

quick-build: ## Build rápido completo: up → build-image
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@echo "$(GREEN)  Quick Build: Up + Build Image$(NC)"
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@make up
	@sleep 2
	@make build-image

# ============================================
# Development
# ============================================

install-tools: ## Instalar herramientas útiles en el contenedor
	$(BUILDER) apt-get update && apt-get install -y \
		build-essential git curl wget

print-config: ## Mostrar configuración actual
	@echo "$(BLUE)╔════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║  Configuración Actual                  ║$(NC)"
	@echo "$(BLUE)╚════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(GREEN)Docker:$(NC)"
	@echo "  Imagen: $$($(DOCKER_COMPOSE) config --images | head -1 || echo 'yocto-qwen:latest')"
	@echo "  Contenedor: $$($(DOCKER_COMPOSE) ps --format 'table {{.Names}}' 2>/dev/null | tail -1 || echo 'No iniciado')"
	@echo ""
	@echo "$(GREEN)Yocto:$(NC)"
	@echo "  Máquina: jetson-nano-devkit"
	@echo "  Distro: poky"
	@echo "  Imagen: jetson-nano-qwen-image"
	@echo ""
	@echo "$(GREEN)Recursos:$(NC)"
	@echo "  Threads: $$(grep BB_NUMBER_THREADS docker-compose.yml | head -1 | awk '{print $$NF}')"
	@echo "  Make: $$(grep PARALLEL_MAKE docker-compose.yml | head -1 | awk '{print $$NF}')"

# ============================================
# Aliases útiles
# ============================================

.PHONY: start stop begin compile compile-fast clean-all
start: up
begin: full-setup
compile: build-image
compile-fast: build-image-fast
clean-all: clean-volumes

# ============================================
# Default
# ============================================

.DEFAULT_GOAL := help
