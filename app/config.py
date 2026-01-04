"""
Docling Knowledge Hub Configuration

Supports multiple environment files:
- .env.local - Private mode with Weaviate (run with ENV_FILE=.env.local)
- .env.saas - SaaS mode with auth/payments (run with ENV_FILE=.env.saas)
- .env - Default (auto-selects based on available services)
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal
from dotenv import load_dotenv

# Load environment variables from specified file or default
env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file, override=True)

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
CHROMADB_DIR = DATA_DIR / "chromadb"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

# Ensure directories exist
for dir_path in [DATA_DIR, UPLOADS_DIR, CHROMADB_DIR, TRANSCRIPTS_DIR, LOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


@dataclass
class ServerConfig:
    """Server configuration"""
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    # Port is hardcoded in Dockerfile CMD, don't read from environment to avoid issues
    port: int = 8200
    debug: bool = False
    workers: int = 1


@dataclass
class DatabaseConfig:
    """Database configuration"""
    sqlite_path: Path = field(default_factory=lambda: DATA_DIR / "knowledge_hub.db")
    chromadb_path: Path = field(default_factory=lambda: CHROMADB_DIR)


@dataclass
class DoclingConfig:
    """Docling document processing configuration"""
    # PDF Pipeline
    pdf_pipeline: Literal["standard", "vlm", "layout"] = "standard"

    # OCR settings
    ocr_enabled: bool = True
    ocr_engine: Literal["easyocr", "tesseract", "tesseract_cli"] = "easyocr"
    ocr_lang: list[str] = field(default_factory=lambda: ["en"])

    # Accelerator
    accelerator: Literal["cpu", "cuda", "mps", "auto"] = "auto"

    # VLM (Vision Language Model)
    vlm_enabled: bool = False
    vlm_model: Literal["granite-docling", "smoldocling"] = "granite-docling"

    # Table detection
    table_structure_enabled: bool = True

    # Image handling
    images_scale: float = 1.0
    generate_page_images: bool = False
    generate_picture_images: bool = False


@dataclass
class ChunkingConfig:
    """Text chunking configuration for RAG"""
    strategy: Literal["fixed", "semantic", "paragraph"] = "paragraph"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100


@dataclass
class WhisperConfig:
    """Whisper transcription configuration"""
    model_size: Literal["tiny", "base", "small", "medium", "large", "turbo"] = "base"
    language: str | None = None  # None for auto-detect
    device: Literal["cpu", "cuda", "auto"] = "auto"
    compute_type: Literal["int8", "float16", "float32"] = "float16"


@dataclass
class YouTubeConfig:
    """YouTube download configuration"""
    # Cookies file path (Netscape format) - for bypassing bot detection
    cookies_file: str = field(default_factory=lambda: os.getenv("YOUTUBE_COOKIES_FILE", ""))
    # Chrome profile for cookie extraction (e.g., "Profile 12")
    chrome_profile: str = field(default_factory=lambda: os.getenv("YOUTUBE_CHROME_PROFILE", "Profile 12"))
    # Use cookies from browser directly (requires browser to be closed or secretstorage)
    cookies_from_browser: bool = field(default_factory=lambda: os.getenv("YOUTUBE_COOKIES_FROM_BROWSER", "false").lower() == "true")

    # Rate limiting settings
    # Delay between video downloads (seconds) - helps avoid rate limiting
    download_delay: int = field(default_factory=lambda: int(os.getenv("YOUTUBE_DOWNLOAD_DELAY", "15")))
    # Maximum retries per video on failure
    max_retries: int = field(default_factory=lambda: int(os.getenv("YOUTUBE_MAX_RETRIES", "3")))
    # Auto-refresh cookies on auth/rate-limit errors
    auto_refresh_cookies: bool = field(default_factory=lambda: os.getenv("YOUTUBE_AUTO_REFRESH_COOKIES", "true").lower() == "true")
    # Minimum seconds between cookie refreshes
    cookie_refresh_interval: int = field(default_factory=lambda: int(os.getenv("YOUTUBE_COOKIE_REFRESH_INTERVAL", "300")))

    @property
    def has_cookies(self) -> bool:
        """Check if any cookie source is configured"""
        return bool(self.cookies_file or (self.cookies_from_browser and self.chrome_profile))


@dataclass
class EmbeddingConfig:
    """Embedding model configuration"""
    model_name: str = "all-MiniLM-L6-v2"
    device: Literal["cpu", "cuda", "auto"] = "auto"


@dataclass
class RAGConfig:
    """RAG enhancement configuration"""
    # Cross-encoder reranking
    reranking_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_RERANKING_ENABLED", "true").lower() == "true"
    )
    reranker_model: str = field(
        default_factory=lambda: os.getenv("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    )
    over_retrieve_factor: int = 3  # Retrieve N times more chunks before reranking

    # HyDE (Hypothetical Document Embeddings)
    hyde_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_HYDE_ENABLED", "true").lower() == "true"
    )
    hyde_model: str = field(
        default_factory=lambda: os.getenv("RAG_HYDE_MODEL", "gpt-4o-mini")
    )

    # Query decomposition for multi-hop queries
    decomposition_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_DECOMPOSITION_ENABLED", "true").lower() == "true"
    )
    decomposition_model: str = field(
        default_factory=lambda: os.getenv("RAG_DECOMPOSITION_MODEL", "gpt-4o-mini")
    )

    # Confidence scoring for out-of-domain detection
    confidence_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_CONFIDENCE_ENABLED", "true").lower() == "true"
    )
    confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "0.35"))
    )
    avg_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("RAG_AVG_CONFIDENCE_THRESHOLD", "0.25"))
    )

    # Adaptive retrieval based on query complexity
    adaptive_retrieval: bool = field(
        default_factory=lambda: os.getenv("RAG_ADAPTIVE_RETRIEVAL", "true").lower() == "true"
    )

    # BM25 Hybrid Search
    bm25_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_BM25_ENABLED", "true").lower() == "true"
    )
    bm25_weight: float = field(
        default_factory=lambda: float(os.getenv("RAG_BM25_WEIGHT", "0.3"))
    )  # 0-1, weight for BM25 vs dense in RRF fusion


@dataclass
class SchedulerConfig:
    """Channel monitoring scheduler configuration"""
    check_interval_hours: int = 48  # Every 2 days
    max_concurrent_jobs: int = 2
    enabled: bool = True


@dataclass
class ChatConfig:
    """Chat/LLM configuration"""
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    max_tokens: int = 4096
    temperature: float = 0.7
    context_chunks: int = 8  # Number of relevant chunks to include
    system_prompt: str = """You are a knowledgeable assistant helping users explore the current knowledge base.
You have access to documents, YouTube transcripts, and web content available in our knowledge archive.

When answering questions:
1. Use the provided context from the knowledge base to give accurate, relevant answers
2. Always cite your sources using footnote numbers [1], [2], etc.
3. If the context doesn't contain enough information, say so honestly
4. Be concise but thorough
5. If asked about topics not in the current knowledge base, indicate that clearly

Remember: You're helping the user understand and explore the current knowledge base.
It's better to admit when information isn't available than to provide incorrect answers."""


@dataclass
class SupabaseConfig:
    """Supabase authentication configuration"""
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))
    service_role_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    jwt_secret: str = field(default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET", ""))

    @property
    def is_configured(self) -> bool:
        """Check if Supabase is properly configured"""
        return bool(self.url and self.anon_key)


@dataclass
class StripeConfig:
    """Stripe payment configuration"""
    secret_key: str = field(default_factory=lambda: os.getenv("STRIPE_SECRET_KEY", ""))
    publishable_key: str = field(default_factory=lambda: os.getenv("STRIPE_PUBLISHABLE_KEY", ""))
    webhook_secret: str = field(default_factory=lambda: os.getenv("STRIPE_WEBHOOK_SECRET", ""))

    # Product IDs
    pro_product_id: str = field(default_factory=lambda: os.getenv("STRIPE_PRO_PRODUCT_ID", ""))
    enterprise_product_id: str = field(default_factory=lambda: os.getenv("STRIPE_ENTERPRISE_PRODUCT_ID", ""))

    # Price IDs
    pro_monthly_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", ""))
    pro_yearly_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_PRO_YEARLY_PRICE_ID", ""))
    enterprise_monthly_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_ENTERPRISE_MONTHLY_PRICE_ID", ""))
    enterprise_yearly_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_ENTERPRISE_YEARLY_PRICE_ID", ""))

    @property
    def is_configured(self) -> bool:
        """Check if Stripe is properly configured"""
        return bool(self.secret_key and self.publishable_key)


@dataclass
class WeaviateConfig:
    """Weaviate vector database configuration (for private mode)"""
    host: str = field(default_factory=lambda: os.getenv("WEAVIATE_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("WEAVIATE_PORT", "8088")))
    grpc_port: int = field(default_factory=lambda: int(os.getenv("WEAVIATE_GRPC_PORT", "8089")))
    enabled: bool = field(default_factory=lambda: os.getenv("WEAVIATE_ENABLED", "false").lower() == "true")

    # Collection/Class to query
    collection_name: str = field(default_factory=lambda: os.getenv("WEAVIATE_COLLECTION", "Business"))

    @property
    def is_configured(self) -> bool:
        """Check if Weaviate is enabled and configured"""
        return self.enabled and bool(self.host)

    @property
    def http_url(self) -> str:
        """Get the HTTP URL for Weaviate"""
        return f"http://{self.host}:{self.port}"


@dataclass
class PgVectorConfig:
    """PostgreSQL + pgvector configuration for MAGICK PDFs"""
    # Connection settings
    host: str = field(default_factory=lambda: os.getenv("PGVECTOR_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("PGVECTOR_PORT", "5433")))
    database: str = field(default_factory=lambda: os.getenv("PGVECTOR_DATABASE", "magick_knowledge"))
    user: str = field(default_factory=lambda: os.getenv("PGVECTOR_USER", "docling"))
    password: str = field(default_factory=lambda: os.getenv("PGVECTOR_PASSWORD", "docling_secure_pwd_2024"))

    # Embedding settings (local BGE model for MAGICK PDFs)
    embedding_model: str = field(default_factory=lambda: os.getenv("PGVECTOR_EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"))
    embedding_dimensions: int = field(default_factory=lambda: int(os.getenv("PGVECTOR_EMBEDDING_DIMENSIONS", "1024")))

    # Processing settings
    chunk_size: int = field(default_factory=lambda: int(os.getenv("PGVECTOR_CHUNK_SIZE", "800")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("PGVECTOR_CHUNK_OVERLAP", "200")))

    # Enable pgvector as RAG backend
    enabled: bool = field(default_factory=lambda: os.getenv("PGVECTOR_ENABLED", "false").lower() == "true")

    @property
    def is_configured(self) -> bool:
        """Check if pgvector is properly configured"""
        return bool(self.host and self.database and self.user)

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RunPodConfig:
    """RunPod serverless transcription configuration"""
    # Enable RunPod for transcription (falls back to local Whisper if disabled)
    enabled: bool = field(default_factory=lambda: os.getenv("RUNPOD_TRANSCRIPTION_ENABLED", "false").lower() == "true")

    # RunPod API key
    api_key: str = field(default_factory=lambda: os.getenv("RUNPOD_API_KEY", ""))

    # Serverless endpoint ID for faster-whisper
    endpoint_id: str = field(default_factory=lambda: os.getenv("RUNPOD_WHISPER_ENDPOINT_ID", ""))

    # Model to use: distil-large-v3 recommended for best speed/quality ratio
    model: str = field(default_factory=lambda: os.getenv("RUNPOD_WHISPER_MODEL", "distil-large-v3"))

    # Public URL where RunPod can fetch audio files from Docling
    public_url: str = field(default_factory=lambda: os.getenv("RUNPOD_PUBLIC_URL", "https://docling-runpod.cyvril.tech"))

    # Timeout for transcription jobs (seconds)
    job_timeout: int = field(default_factory=lambda: int(os.getenv("RUNPOD_JOB_TIMEOUT", "600")))

    # Poll interval when waiting for job completion (seconds)
    poll_interval: float = field(default_factory=lambda: float(os.getenv("RUNPOD_POLL_INTERVAL", "2.0")))

    # Secret token for audio file access (prevents unauthorized access)
    audio_token: str = field(default_factory=lambda: os.getenv("RUNPOD_AUDIO_TOKEN", ""))

    @property
    def is_configured(self) -> bool:
        """Check if RunPod is properly configured"""
        return self.enabled and bool(self.api_key and self.endpoint_id)


@dataclass
class AppModeConfig:
    """Application mode configuration"""
    # Private mode disables auth requirements and enables personal data sources
    private_mode: bool = field(default_factory=lambda: os.getenv("PRIVATE_MODE", "false").lower() == "true")

    # Auth required - if False, all routes are public
    auth_required: bool = field(default_factory=lambda: os.getenv("AUTH_REQUIRED", "true").lower() == "true")

    # TWA Dev Mode - bypasses Telegram auth for browser testing
    # Uses TWA_DEV_TELEGRAM_ID as the test user (default: 1069852438 - owner)
    twa_dev_mode: bool = field(default_factory=lambda: os.getenv("TWA_DEV_MODE", "false").lower() == "true")
    twa_dev_telegram_id: int = field(default_factory=lambda: int(os.getenv("TWA_DEV_TELEGRAM_ID", "1069852438")))


@dataclass
class AppConfig:
    """Main application configuration"""
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    docling: DoclingConfig = field(default_factory=DoclingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    stripe: StripeConfig = field(default_factory=StripeConfig)
    weaviate: WeaviateConfig = field(default_factory=WeaviateConfig)
    runpod: RunPodConfig = field(default_factory=RunPodConfig)
    pgvector: PgVectorConfig = field(default_factory=PgVectorConfig)
    mode: AppModeConfig = field(default_factory=AppModeConfig)


# Global config instance
config = AppConfig()


# Supported file extensions
SUPPORTED_DOCUMENT_FORMATS = {
    ".pdf": "PDF Document",
    ".docx": "Word Document",
    ".doc": "Word Document (Legacy)",
    ".pptx": "PowerPoint Presentation",
    ".ppt": "PowerPoint (Legacy)",
    ".xlsx": "Excel Spreadsheet",
    ".xls": "Excel (Legacy)",
    ".html": "HTML Document",
    ".htm": "HTML Document",
    ".md": "Markdown",
    ".txt": "Plain Text",
    ".rtf": "Rich Text Format",
    ".png": "PNG Image",
    ".jpg": "JPEG Image",
    ".jpeg": "JPEG Image",
    ".tiff": "TIFF Image",
    ".tif": "TIFF Image",
    ".bmp": "BMP Image",
    ".webp": "WebP Image",
}

SUPPORTED_AUDIO_FORMATS = {
    ".mp3": "MP3 Audio",
    ".wav": "WAV Audio",
    ".m4a": "M4A Audio",
    ".ogg": "OGG Audio",
    ".flac": "FLAC Audio",
    ".webm": "WebM Audio/Video",
    ".mp4": "MP4 Video",
}
