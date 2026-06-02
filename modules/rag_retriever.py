"""
modules/rag_retriever.py
------------------------
Módulo de Recuperación Aumentada por Generación (RAG) — backend TF-IDF offline.

QUÉ HACE:
  Dado un texto de consulta, busca los fragmentos de documentos locales
  más relevantes y los retorna para inyectarlos en el contexto del LLM.

POR QUÉ SE CAMBIÓ EL BACKEND (ChromaDB → TF-IDF + numpy):
  La versión anterior usaba sentence-transformers (all-MiniLM-L6-v2).
  Ese modelo requiere descargarse desde internet (~80 MB) y genera
  embeddings con CUDA 11.x — incompatible con la GPU Maxwell del Jetson
  Nano B01 que sólo soporta CUDA 10.2 / JetPack 4.6.x.

  El nuevo backend usa:
    - sklearn.TfidfVectorizer  → parte de meta-python en Yocto, sin descarga
    - numpy                    → ya requerido por OpenCV en el sistema
    - pickle / json            → stdlib de Python 3.9

  El índice (docs.json, embeddings.npy, vectorizer.pkl) se construye
  una sola vez en PC con scripts/build_rag_index.py y se incluye como
  archivo estático en la imagen Yocto.  En Jetson sólo se hace la
  multiplicación de matrices de la query contra el índice (~3.9 MB RAM).

INTERFAZ PÚBLICA (sin cambios respecto a la versión anterior):
  retriever = RAGRetriever()
  fragmentos = retriever.retrieve("manchas negras en hojas de papa", n=2)
  fragmentos = retriever.retrieve_para_modo("diagnostico_fitosanitario")
  retriever.disponible  → bool

NOTAS SOBRE SIMILITUD:
  Los scores TF-IDF coseno son típicamente 0.05–0.20 para un corpus pequeño
  (126 chunks × 8000 vocab).  El umbral mínimo se fija en 0.03 para no
  filtrar fragmentos válidos.  El umbral de sentence-transformers (0.35)
  NO aplica aquí — usarlo produciría 0 resultados en todos los casos.
"""

import json
import logging
import os
import pickle
from typing import Optional

import numpy as np
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

# ── Rutas por defecto ────────────────────────────────────────────────────────
RAG_INDEX_PATH   = "rag/index"
DOCS_FILENAME    = "docs.json"
EMB_FILENAME     = "embeddings.npy"
VECT_FILENAME    = "vectorizer.pkl"

# Umbral mínimo de similitud coseno para incluir un fragmento.
# TF-IDF produce scores 0.05–0.20; umbral de 0.03 evita filtrar
# fragmentos válidos pero descarta ruido puro (score ≈ 0.00).
SIM_THRESHOLD = 0.03

# Queries de recuperación automática por modo (usadas en retrieve_para_modo)
QUERIES_POR_MODO = {
    "diagnostico_fitosanitario": (
        "enfermedades papa síntomas hojas manchas tizón fusariosis Costa Rica"
    ),
    "riego_fertilizacion": (
        "riego fertilización papa humedad suelo nitrógeno potasio fósforo Cartago"
    ),
    "economia": (
        "precios papa PIMA Costa Rica colones calidad primera segunda tercera rentabilidad"
    ),
}


class RAGRetriever:
    """
    Recuperador de contexto RAG — backend TF-IDF + similitud coseno.

    Diseñado para funcionar completamente offline en ARM64 (Jetson Nano B01)
    sin necesitar internet ni modelos de embeddings neuronales adicionales.

    Uso:
        rag = RAGRetriever()                           # carga índice
        frags = rag.retrieve("manchas en hojas", n=2) # recupera fragmentos
        frags = rag.retrieve_para_modo("economia")    # query automática
    """

    def __init__(
        self,
        index_path: str = RAG_INDEX_PATH,
        # model_name se ignora en este backend pero se acepta para
        # compatibilidad con el parámetro que viene de settings.yaml
        model_name: str = "",
    ):
        self._index_path = index_path
        self._docs: list[dict] = []
        self._embeddings: Optional[np.ndarray] = None
        self._vectorizer = None
        self._disponible = False
        self._intentar_inicializar()

    # ── Inicialización ───────────────────────────────────────────────────────

    def _intentar_inicializar(self) -> None:
        """Carga el índice TF-IDF pre-construido desde disco."""
        docs_path  = os.path.join(self._index_path, DOCS_FILENAME)
        emb_path   = os.path.join(self._index_path, EMB_FILENAME)
        vect_path  = os.path.join(self._index_path, VECT_FILENAME)

        faltantes = [p for p in (docs_path, emb_path, vect_path)
                     if not os.path.exists(p)]
        if faltantes:
            logger.warning(
                "Índice RAG incompleto en '%s'. Archivos faltantes: %s\n"
                "  → Ejecutá: python3 scripts/build_rag_index.py",
                self._index_path,
                ", ".join(os.path.basename(p) for p in faltantes),
            )
            return

        try:
            with open(docs_path, encoding="utf-8") as f:
                self._docs = json.load(f)

            self._embeddings = np.load(emb_path).astype(np.float32)

            with open(vect_path, "rb") as f:
                self._vectorizer = pickle.load(f)

            self._disponible = True
            logger.info(
                "RAG inicializado: %d chunks | vocab=%d | RAM=%.1f MB",
                len(self._docs),
                self._embeddings.shape[1],
                self._embeddings.nbytes / 1024 / 1024,
            )

        except Exception as e:
            logger.warning("RAG falló al inicializar: %s", e)
            self._disponible = False

    # ── API pública ──────────────────────────────────────────────────────────

    @property
    def disponible(self) -> bool:
        return self._disponible

    def retrieve(self, query: str, n: int = 2) -> list[dict]:
        """
        Recupera los n fragmentos más relevantes para la consulta.

        Args:
            query: Texto de la consulta del agricultor.
            n:     Número máximo de fragmentos a retornar.

        Returns:
            Lista de dicts con claves: id, fuente, seccion, texto.
            Lista vacía si el RAG no está disponible o no hay resultados
            sobre el umbral de similitud.
        """
        if not self._disponible:
            return []

        try:
            # Vectorizar query con el mismo vectorizador del índice
            q_sparse = self._vectorizer.transform([query])
            q_norm   = normalize(q_sparse, norm="l2").toarray().astype(np.float32)

            # Similitud coseno: dot product (embeddings ya están normalizados)
            scores = (self._embeddings @ q_norm.T).flatten()

            # Top-n por encima del umbral mínimo
            top_idx = scores.argsort()[::-1][:n]
            fragmentos = [
                dict(self._docs[i])          # copia para no mutar el índice
                for i in top_idx
                if scores[i] >= SIM_THRESHOLD
            ]

            logger.info(
                "RAG: %d/%d fragmentos recuperados (threshold=%.2f) "
                "para query '%.40s...'",
                len(fragmentos), n, SIM_THRESHOLD, query,
            )
            return fragmentos

        except Exception as e:
            logger.error("Error en RAG.retrieve(): %s", e)
            return []

    def retrieve_para_modo(
        self,
        modo: str,
        datos_extra: Optional[str] = None,
    ) -> list[dict]:
        """
        Construye automáticamente la query de recuperación según el modo
        activo del sistema.  Útil cuando el agricultor no escribe una
        pregunta libre y se quiere inyectar contexto relevante de todas
        formas.

        Args:
            modo:        diagnostico_fitosanitario | riego_fertilizacion | economia
            datos_extra: Texto adicional a concatenar (enfermedad detectada,
                         etapa fenológica, etc.)

        Returns:
            Lista de dicts con fragmentos relevantes (mismo formato que
            retrieve()).
        """
        query = QUERIES_POR_MODO.get(modo, "cultivo papa Costa Rica")
        if datos_extra and datos_extra.strip():
            query = f"{query} {datos_extra.strip()}"
        return self.retrieve(query, n=2)