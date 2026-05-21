.PHONY: help build up down logs test benchmark clean rebuild shell validate

# Variables
DOCKER_COMPOSE := docker compose
PYTHON := python
IMAGE_NAME := agri-edge-ia
CONTAINER_APP := agri-edge-ia
CONTAINER_OLLAMA := agri-ollama

help: ## Muestra este help
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  AGRI-EDGE-IA — Docker Commands                             ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Ejemplos:"
	@echo "  make build           # Construir imagen"
	@echo "  make up              # Iniciar servicios"
	@echo "  make down            # Detener servicios"
	@echo "  make test            # Ejecutar Fase 0"
	@echo "  make logs-app        # Ver logs de app"
	@echo ""

# ────────────────────────────────────────────────────────────────────────

build: ## Construir imagen Docker
	@echo "🔨 Construyendo imagen $(IMAGE_NAME)..."
	$(DOCKER_COMPOSE) build --no-cache agri-edge-ia
	@echo "✓ Imagen construida"

build-quick: ## Construir sin cache (más rápido)
	@echo "🔨 Construyendo imagen (rápido)..."
	$(DOCKER_COMPOSE) build agri-edge-ia

up: ## Iniciar todos los servicios (Ollama + App)
	@echo "🚀 Iniciando servicios..."
	$(DOCKER_COMPOSE) up -d
	@echo "✓ Servicios iniciados"
	@echo ""
	@echo "Espera 30 segundos a que Ollama esté listo..."
	@sleep 30
	@echo "✓ Listo. Ejecuta: make test"

down: ## Detener todos los servicios
	@echo "🛑 Deteniendo servicios..."
	$(DOCKER_COMPOSE) down
	@echo "✓ Servicios detenidos"

restart: ## Reiniciar servicios
	@echo "🔄 Reiniciando servicios..."
	$(DOCKER_COMPOSE) restart
	@echo "✓ Servicios reiniciados"

# ────────────────────────────────────────────────────────────────────────

validate: ## Validar setup (checksum, dependencias)
	@echo "✓ Validando setup..."
	docker exec $(CONTAINER_APP) python scripts/validate_setup.py

test: ## Ejecutar Fase 0 (validación Ollama + modelo)
	@echo "🧪 Ejecutando Fase 0..."
	docker exec $(CONTAINER_APP) python scripts/test_ollama.py
	@echo "✓ Fase 0 completada"

test-interactive: ## Ejecutar test interactivo
	@echo "🧪 Test interactivo..."
	docker exec -it $(CONTAINER_APP) python scripts/test_ollama.py

benchmark: ## Ejecutar benchmark de latencia
	@echo "📊 Ejecutando benchmarks..."
	docker exec $(CONTAINER_APP) python scripts/benchmark_llm.py --runs 5

rag-build: ## Construir índice RAG
	@echo "🔍 Construyendo RAG index..."
	docker exec $(CONTAINER_APP) python scripts/build_rag_index.py
	@echo "✓ RAG index construido"

main: ## Ejecutar main.py (interfaz interactiva)
	@echo "🎯 Iniciando AGRI-EDGE-IA CLI..."
	docker exec -it $(CONTAINER_APP) python main.py

# ────────────────────────────────────────────────────────────────────────

logs: ## Ver logs de ambos servicios
	$(DOCKER_COMPOSE) logs -f

logs-app: ## Ver logs solo de app
	@echo "📋 Logs de AGRI-EDGE-IA:"
	docker logs -f $(CONTAINER_APP)

logs-ollama: ## Ver logs solo de Ollama
	@echo "📋 Logs de Ollama:"
	docker logs -f $(CONTAINER_OLLAMA)

logs-tail: ## Ver últimas 50 líneas de logs
	docker logs --tail 50 $(CONTAINER_APP)

# ────────────────────────────────────────────────────────────────────────

shell: ## Abrir shell interactivo en app
	@echo "🐚 Abriendo shell en $(CONTAINER_APP)..."
	docker exec -it $(CONTAINER_APP) /bin/bash

shell-ollama: ## Abrir shell en Ollama
	docker exec -it $(CONTAINER_OLLAMA) /bin/bash

# ────────────────────────────────────────────────────────────────────────

ps: ## Ver estado de contenedores
	@echo "📦 Estado de contenedores:"
	docker ps --filter "name=agri" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

stats: ## Ver uso de recursos (CPU, RAM)
	@echo "📊 Recursos de contenedores:"
	docker stats --no-stream $(CONTAINER_APP) $(CONTAINER_OLLAMA)

# ────────────────────────────────────────────────────────────────────────

pull-model: ## Descargar modelo Ollama (qwen2.5:3b)
	@echo "⬇️  Descargando modelo qwen2.5:3b..."
	docker exec $(CONTAINER_OLLAMA) ollama pull qwen2.5:3b
	@echo "✓ Modelo descargado"

list-models: ## Listar modelos disponibles en Ollama
	docker exec $(CONTAINER_OLLAMA) ollama list

test-model: ## Probar modelo manualmente
	@echo "🧪 Probando modelo..."
	docker exec $(CONTAINER_OLLAMA) ollama run qwen2.5:3b "¿Cuál es la principal enfermedad del cultivo de papa?"

# ────────────────────────────────────────────────────────────────────────

clean: ## Limpiar contenedores y volúmenes (CUIDADO)
	@echo "🧹 Limpiando Docker..."
	$(DOCKER_COMPOSE) down -v
	@echo "✓ Limpieza completada"
	@echo "⚠️  Nota: Se eliminaron volúmenes. Datos perdidos."

prune: ## Eliminar imágenes/contenedores no usados
	@echo "🧹 Ejecutando docker prune..."
	docker system prune -f
	@echo "✓ Limpieza completada"

rebuild: ## Rebuild completo (clean + build + up)
	@echo "🔄 Rebuild completo..."
	make clean
	make build
	make up
	@echo "✓ Rebuild completado"

# ────────────────────────────────────────────────────────────────────────

version: ## Ver versiones de herramientas
	@echo "Versiones instaladas:"
	docker --version
	docker compose --version
	$(PYTHON) --version

check-docker: ## Verificar que Docker está funcionando
	@echo "Verificando Docker..."
	@docker ps > /dev/null && echo "✓ Docker OK" || echo "✗ Docker NO disponible"
	@docker compose --version > /dev/null && echo "✓ Docker Compose OK" || echo "✗ Docker Compose NO disponible"

# ────────────────────────────────────────────────────────────────────────

push: ## Push de imagen a registry (configura REGISTRY)
	@echo "📤 Pusheando imagen..."
	docker tag $(IMAGE_NAME):latest registry.example.com/$(IMAGE_NAME):latest
	docker push registry.example.com/$(IMAGE_NAME):latest

# ────────────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help
