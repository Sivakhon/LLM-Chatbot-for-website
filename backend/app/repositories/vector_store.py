"""ChromaDB client factory."""

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings

from app.core.config import Settings


def create_chroma_client(settings: Settings) -> ClientAPI:
    chroma_settings = ChromaSettings(anonymized_telemetry=False)
    match settings.chroma_mode:
        case "http":
            return chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port, settings=chroma_settings
            )
        case "persistent":
            settings.chroma_path.mkdir(parents=True, exist_ok=True)
            return chromadb.PersistentClient(
                path=str(settings.chroma_path), settings=chroma_settings
            )
        case "memory":
            return chromadb.EphemeralClient(settings=chroma_settings)
