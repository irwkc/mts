import hashlib
import time
import os
import chromadb

# Используем постоянную базу данных на диске
CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

_client = None

def get_client():
    global _client
    if _client is None:
        try:
            from chromadb.config import Settings
            _client = chromadb.HttpClient(
                host=CHROMA_HOST, 
                port=CHROMA_PORT,
                settings=Settings(anonymized_telemetry=False)
            )
        except Exception as e:
            print(f"Warning: could not connect to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT} - {e}")
    return _client

def _get_collection_name(user_id: str) -> str:
    # Преобразуем id в безопасный вид
    safe_hash = hashlib.md5(user_id.encode()).hexdigest()[:16]
    return f"user_mem_{safe_hash}"

def save_message(user_id: str, role: str, content: str) -> None:
    client = get_client()
    if not client or not content.strip():
        return
        
    try:
        col = client.get_or_create_collection(_get_collection_name(user_id))
        doc_id = hashlib.md5(f"{time.time()}_{content}".encode()).hexdigest()
        
        col.add(
            documents=[content[:8000]],
            metadatas=[{"role": role, "ts": time.time()}],
            ids=[doc_id]
        )
    except Exception as e:
        print(f"Error saving to memory: {e}")

def recall(user_id: str, query: str, n_results: int = 5) -> list[str]:
    client = get_client()
    if not client or not query.strip():
        return []
        
    try:
        col = client.get_or_create_collection(_get_collection_name(user_id))
        if col.count() == 0:
            return []
            
        n = min(n_results, max(1, col.count()))
        results = col.query(query_texts=[query[:2000]], n_results=n)
        
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        
        lines = []
        for d, m in zip(docs, metas):
            if isinstance(d, str):
                role = m.get("role", "unknown")
                lines.append(f"{role}: {d}")
        return lines
    except Exception as e:
        print(f"Error recalling from memory: {e}")
        return []
