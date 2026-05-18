"""
scripts/build_rag_index.py
--------------------------
Construye el índice vectorial RAG a partir de los documentos en rag/documentos/.

CUÁNDO EJECUTAR:
  - Una sola vez en la PC de desarrollo, ANTES de armar la imagen Yocto.
  - Cada vez que se actualicen los documentos de rag/documentos/.
  - NUNCA en el Jetson Nano (el índice se copia como archivo estático).

POR QUÉ EN PC Y NO EN JETSON:
  Generar embeddings para todos los chunks toma 2-5 minutos en CPU.
  En Jetson sería más lento y consumiría RAM que necesita el LLM.
  El índice resultante (rag/index/chroma.sqlite3) va en la imagen Yocto
  como cualquier otro archivo estático.

FLUJO:
  1. Lee todos los .txt de rag/documentos/
  2. Los divide en chunks de 200 palabras con overlap de 30
  3. Genera embeddings con all-MiniLM-L6-v2 (80 MB, corre en CPU)
  4. Guarda en ChromaDB con backend SQLite en rag/index/

USO:
  pip install chromadb sentence-transformers
  python scripts/build_rag_index.py
  python scripts/build_rag_index.py --docs-dir rag/documentos --index-dir rag/index
  python scripts/build_rag_index.py --test   # verifica con 3 queries de prueba
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHUNK_SIZE_PALABRAS = 200   # palabras por fragmento
CHUNK_OVERLAP = 30          # palabras de solapamiento entre fragmentos consecutivos
COLLECTION_NAME = "agri_edge_cr"
MODEL_NAME = "all-MiniLM-L6-v2"


def leer_documentos(docs_dir: str) -> list[dict]:
    """Lee todos los archivos .txt del directorio y retorna lista de {filename, content}."""
    path = Path(docs_dir)
    documentos = []
    patrones = list(path.glob("*.txt")) + list(path.glob("*.md"))
    for archivo in sorted(patrones, key=lambda x: x.name):
        try:
            contenido = archivo.read_text(encoding="utf-8")
            documentos.append({"nombre": archivo.name, "contenido": contenido})
            logger.info("  Leído: %s (%d chars)", archivo.name, len(contenido))
        except Exception as e:
            logger.warning("No se pudo leer %s: %s", archivo.name, e)
    return documentos


def dividir_en_chunks(texto: str, fuente: str,
                       chunk_size: int = CHUNK_SIZE_PALABRAS,
                       overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Divide el texto en chunks de tamaño fijo con overlap.

    El overlap (solapamiento) garantiza que ideas que cruzan el límite entre
    dos chunks no se pierdan. Si un chunk termina en medio de una frase,
    el siguiente chunk repite las últimas 'overlap' palabras.
    """
    palabras = texto.split()
    chunks = []
    inicio = 0

    while inicio < len(palabras):
        fin = min(inicio + chunk_size, len(palabras))
        chunk_texto = " ".join(palabras[inicio:fin])
        chunks.append({
            "texto": chunk_texto,
            "fuente": fuente,
            "chunk_inicio": inicio,
            "chunk_fin": fin,
        })
        if fin >= len(palabras):
            break
        inicio += chunk_size - overlap

    return chunks


def construir_indice(docs_dir: str, index_dir: str) -> None:
    """Construye el índice ChromaDB completo."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.error("Instalar dependencias: pip install chromadb sentence-transformers")
        sys.exit(1)

    # Limpiar índice anterior si existe
    index_path = Path(index_dir)
    if index_path.exists():
        import shutil
        shutil.rmtree(index_path)
        logger.info("Índice anterior eliminado.")
    index_path.mkdir(parents=True, exist_ok=True)

    # Inicializar ChromaDB con backend SQLite persistente
    client = chromadb.PersistentClient(path=str(index_path))
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # distancia coseno para similitud semántica
    )

    # Cargar modelo de embeddings
    logger.info("Cargando modelo de embeddings '%s'...", MODEL_NAME)
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME)
    logger.info("Modelo cargado en %.1fs", time.time() - t0)

    # Leer documentos y generar chunks
    documentos = leer_documentos(docs_dir)
    if not documentos:
        logger.error("No se encontraron archivos .txt en '%s'", docs_dir)
        sys.exit(1)

    todos_chunks = []
    for doc in documentos:
        chunks = dividir_en_chunks(doc["contenido"], doc["nombre"])
        todos_chunks.extend(chunks)
        logger.info("  %s → %d chunks", doc["nombre"], len(chunks))

    logger.info("Total: %d chunks a indexar.", len(todos_chunks))

    # Generar embeddings y guardar en ChromaDB por lotes
    BATCH = 32
    total_guardados = 0
    t0 = time.time()

    for i in range(0, len(todos_chunks), BATCH):
        lote = todos_chunks[i:i + BATCH]
        textos = [c["texto"] for c in lote]
        embeddings = model.encode(textos).tolist()

        collection.add(
            ids=[f"chunk_{i + j}" for j in range(len(lote))],
            embeddings=embeddings,
            documents=textos,
            metadatas=[{"source": c["fuente"], "start": c["chunk_inicio"]} for c in lote],
        )
        total_guardados += len(lote)
        logger.info("  Indexados %d/%d chunks...", total_guardados, len(todos_chunks))

    elapsed = time.time() - t0
    logger.info("Índice construido: %d fragmentos en %.1fs", total_guardados, elapsed)
    logger.info("   Guardado en: %s", index_path.resolve())


def verificar_indice(index_dir: str) -> None:
    """Ejecuta 3 queries de prueba para verificar que el índice funciona."""
    from modules.rag_retriever import RAGRetriever

    retriever = RAGRetriever(index_path=index_dir)
    if not retriever.disponible:
        logger.error("Índice no disponible para verificación.")
        return

    queries_prueba = [
        "manchas negras en hojas de papa tizón tardío",
        "cuánta agua necesita la papa en tuberización",
        "precio de la papa en PIMA Costa Rica",
    ]

    print("\n" + "=" * 60)
    print("  VERIFICACIÓN DEL ÍNDICE RAG")
    print("=" * 60)

    for query in queries_prueba:
        print(f"\n🔍 Query: '{query}'")
        resultados = retriever.retrieve(query, n=2)
        for r in resultados:
            print(f"   Fuente: {r['fuente']}")
            print(f"   Texto:  {r['texto'][:120]}...")
        if not resultados:
            print("Sin resultados relevantes")

    print("\n Verificación completada.")


def main():
    parser = argparse.ArgumentParser(description="Construye el índice RAG para AGRI-EDGE-IA")
    parser.add_argument("--docs-dir", default="rag/documentos")
    parser.add_argument("--index-dir", default="rag/index")
    parser.add_argument("--test", action="store_true",
                        help="Solo verificar el índice existente, no reconstruir")
    args = parser.parse_args()

    if args.test:
        verificar_indice(args.index_dir)
    else:
        logger.info("Construyendo índice RAG...")
        logger.info("  Documentos: %s", args.docs_dir)
        logger.info("  Índice:     %s", args.index_dir)
        construir_indice(args.docs_dir, args.index_dir)
        verificar_indice(args.index_dir)
        print("\n Para Yocto: copiar la carpeta 'rag/index/' en la imagen como archivo estático.")
        print("   Ruta destino en Jetson: /opt/agri-edge-ia/rag/index/")


if __name__ == "__main__":
    main()