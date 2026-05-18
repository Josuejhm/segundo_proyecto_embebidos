"""
modules/rag_retriever.py
------------------------
Módulo de Recuperación Aumentada por Generación (RAG) offline.

QUÉ HACE:
  Dado un texto de consulta, busca los fragmentos de documentos locales
  más relevantes y los retorna para inyectarlos en el contexto del LLM.

POR QUÉ EXISTE:
  qwen2.5:3b (y cualquier modelo pequeño) no conoce detalles específicos de:
  - Precios PIMA de Costa Rica
  - Variedades locales de papa (La Floresta)
  - Productos SENASA autorizados en CR
  - Condiciones climáticas de Tierra Blanca de Cartago
  Con RAG, la aplicación recupera esta información de documentos locales
  y se la inyecta al modelo antes de que responda. No necesita internet.

CÓMO FUNCIONA:
  1. En PC (una vez): build_rag_index.py convierte documentos TXT a vectores
     y guarda el índice en rag/index/
  2. En Jetson (cada consulta): RAGRetriever carga el índice pre-construido,
     convierte la consulta a vector, busca los 2 fragmentos más similares.

DEPENDENCIAS:
  chromadb>=0.4.0      (base de datos vectorial, backend SQLite, sin servidor)
  sentence-transformers>=2.2.0  (modelo de embeddings all-MiniLM-L6-v2, 80 MB)

COMPATIBILIDAD JETSON:
  ChromaDB usa SQLite como backend → funciona en microSD ext4.
  sentence-transformers corre en CPU (ARM64), sin necesitar CUDA.
  El índice se construye en PC y se copia a la imagen Yocto como archivo estático.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Rutas por defecto (sobreescribibles desde settings.yaml)
RAG_INDEX_PATH = "rag/index"
RAG_MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "agri_edge_cr"


class RAGRetriever:
    """
    Recuperador de contexto RAG usando ChromaDB + sentence-transformers.

    Uso:
        retriever = RAGRetriever()
        fragmentos = retriever.retrieve("manchas negras en hojas de papa", n=2)
    """

    def __init__(
        self,
        index_path: str = RAG_INDEX_PATH,
        model_name: str = RAG_MODEL_NAME,
    ):
        self.index_path = index_path
        self.model_name = model_name
        self._collection = None
        self._model = None
        self._disponible = False
        self._intentar_inicializar()

    def _intentar_inicializar(self) -> None:
        """
        Intenta inicializar ChromaDB y el modelo de embeddings.
        Si fallan (dependencias no instaladas o índice inexistente),
        marca el RAG como no disponible en lugar de lanzar excepción.
        El sistema sigue funcionando sin RAG en ese caso.
        """
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            if not os.path.exists(self.index_path):
                logger.warning(
                    "Índice RAG no encontrado en '%s'. "
                    "Ejecuta: python scripts/build_rag_index.py",
                    self.index_path,
                )
                return

            # Cargar índice pre-construido (no genera vectores aquí)
            client = chromadb.PersistentClient(path=self.index_path)
            colecciones = [c.name for c in client.list_collections()]
            if COLLECTION_NAME not in colecciones:
                logger.warning("Colección '%s' no encontrada en el índice.", COLLECTION_NAME)
                return

            self._collection = client.get_collection(COLLECTION_NAME)
            # Modelo de embeddings liviano: 80 MB, corre en CPU ARM64
            self._model = SentenceTransformer(self.model_name)
            self._disponible = True
            doc_count = self._collection.count()
            logger.info("RAG inicializado: %d fragmentos en índice.", doc_count)

        except ImportError:
            logger.warning(
                "RAG no disponible: instalar chromadb y sentence-transformers. "
                "pip install chromadb sentence-transformers"
            )
        except Exception as e:
            logger.warning("RAG falló al inicializar: %s", e)

    @property
    def disponible(self) -> bool:
        return self._disponible

    def retrieve(self, query: str, n: int = 2) -> list[dict]:
        """
        Recupera los n fragmentos más relevantes para la consulta.

        Args:
            query: Texto de la consulta del agricultor o del modo activo.
            n: Número de fragmentos a retornar (máximo 3 para no saturar tokens).

        Returns:
            Lista de dicts con 'fuente' y 'texto'. Lista vacía si RAG no disponible.
        """
        if not self._disponible:
            return []

        try:
            # Convertir consulta a vector (mismo modelo que se usó para construir el índice)
            embedding = self._model.encode(query).tolist()

            resultados = self._collection.query(
                query_embeddings=[embedding],
                n_results=min(n, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            fragmentos = []
            for doc, meta, dist in zip(
                resultados["documents"][0],
                resultados["metadatas"][0],
                resultados["distances"][0],
            ):
                # Filtrar por distancia: > 1.5 significa poca relevancia
                if dist < 1.5:
                    fragmentos.append({
                        "fuente": meta.get("source", "desconocido"),
                        "texto": doc.strip(),
                    })
                    logger.debug("RAG hit: dist=%.3f fuente=%s", dist, meta.get("source"))
                else:
                    logger.debug("RAG descartado por baja relevancia: dist=%.3f", dist)

            logger.info("RAG: %d fragmentos recuperados para query '%s...'",
                        len(fragmentos), query[:40])
            return fragmentos

        except Exception as e:
            logger.error("Error en RAG retrieve: %s", e)
            return []

    def retrieve_para_modo(self, modo: str, datos_extra: Optional[str] = None) -> list[dict]:
        """
        Construye automáticamente la query de recuperación según el modo activo.
        Útil cuando el agricultor no escribe una pregunta libre.

        Args:
            modo: diagnostico_fitosanitario | riego_fertilizacion | economia
            datos_extra: contexto adicional (enfermedad detectada, etapa, etc.)
        """
        queries_por_modo = {
            "diagnostico_fitosanitario": "enfermedades papa síntomas hojas manchas tizón fusariosis Costa Rica",
            "riego_fertilizacion": "riego fertilización papa humedad suelo nitrógeno potasio fósforo Cartago",
            "economia": "precios papa PIMA Costa Rica colones calidad primera segunda tercera rentabilidad",
        }
        query = queries_por_modo.get(modo, "cultivo papa Costa Rica")
        if datos_extra:
            query = f"{query} {datos_extra}"
        return self.retrieve(query, n=2)