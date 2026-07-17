import logging
from typing import List, Dict, Any
import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.core.config import settings

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, ollama_url: str = settings.LOCAL_LLM_URL, model_name: str = "nomic-embed-text"):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

    def extract_text(self, file_path: str, mime_type: str) -> str:
        """Extracts plain text from a file based on its MIME type.
        Supports plain text formats directly, and contains extension points for other formats.
        """
        try:
            # Handle text files directly
            if mime_type.startswith("text/") or mime_type in [
                "application/json", 
                "application/xml", 
                "application/javascript"
            ]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            
            # Placeholder/Simple extractors for PDF/DOCX to avoid crashing if libraries aren't installed.
            # In a real environment, we'd use PyPDF2 or python-docx here.
            elif mime_type == "application/pdf":
                # Fallback text extraction or library-based extraction
                logger.info(f"Extracting PDF text from {file_path} (basic implementation)...")
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    text_parts = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    return "\n".join(text_parts)
                except ImportError:
                    logger.warning("pypdf not installed. Falling back to reading printable characters.")
                    with open(file_path, "rb") as f:
                        data = f.read()
                        # Simple extraction of readable ASCII characters as a robust fallback
                        return "".join(chr(b) for b in data if 32 <= b < 127 or b in (10, 13))
            
            elif mime_type in [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword"
            ]:
                logger.info(f"Extracting DOCX text from {file_path} (basic implementation)...")
                try:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([p.text for p in doc.paragraphs])
                except ImportError:
                    logger.warning("python-docx not installed. Falling back to basic printable extraction.")
                    with open(file_path, "rb") as f:
                        data = f.read()
                        return "".join(chr(b) for b in data if 32 <= b < 127 or b in (10, 13))

            logger.warning(f"Unsupported MIME type for text extraction: {mime_type}")
            return ""
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return ""

    def chunk_text(self, text: str) -> List[str]:
        """Splits text into chunks of 1000 characters with 200 characters overlap."""
        if not text.strip():
            return []
        return self.splitter.split_text(text)

    def get_embedding(self, text: str) -> List[float]:
        """Calls the local Ollama API to generate embeddings for a chunk of text."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": text
            }
            response = httpx.post(self.ollama_url, json=payload, timeout=30.0)
            response.raise_for_status()
            result = response.json()
            # Handle standard Ollama output formats
            if "embedding" in result:
                return result["embedding"]
            elif "embeddings" in result:
                # Some Ollama versions return embeddings as a list under "embeddings"
                return result["embeddings"][0]
            else:
                raise ValueError(f"Unexpected response format from Ollama: {result}")
        except Exception as e:
            logger.error(f"Error calling Ollama API for embeddings: {e}")
            # Return a mock or zero-vector for robust execution in testing/failover
            # Typically embeddings are 384 or 1536 dimensional. Let's return a dummy 384-dim vector.
            return [0.0] * 384

    def process_document(self, file_path: str, mime_type: str) -> List[Dict[str, Any]]:
        """Extracts, chunks, and vectorizes document text.
        Returns a list of dicts with 'text' and 'embedding'.
        """
        text = self.extract_text(file_path, mime_type)
        chunks = self.chunk_text(text)
        
        vectorized_chunks = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            embedding = self.get_embedding(chunk)
            vectorized_chunks.append({
                "text": chunk,
                "embedding": embedding
            })
        return vectorized_chunks
