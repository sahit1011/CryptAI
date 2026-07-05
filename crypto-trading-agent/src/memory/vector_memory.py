"""
Vector Memory Store
Semantic memory for pattern matching using ChromaDB
"""
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from loguru import logger
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
import os

# Per-request timeout (seconds) for OpenAI embedding calls so a hung
# network request can't block trade persistence indefinitely.
EMBEDDING_TIMEOUT_SECONDS = 15.0
# Number of attempts (initial try + retries) for transient embedding failures.
EMBEDDING_MAX_ATTEMPTS = 3


def cosine_distance_to_similarity(distance: float) -> float:
    """Map a ChromaDB cosine *distance* to a cosine *similarity* score.

    ChromaDB (with ``hnsw:space="cosine"``) returns ``distance = 1 - cosine_similarity``.
    Therefore ``similarity = 1 - distance``. For unit-normalized embeddings this
    yields the familiar [-1, 1] cosine range; identical vectors give distance 0 ->
    similarity 1.0. Pure and unit-testable.
    """
    return 1.0 - float(distance)

@dataclass
class SimilarTrade:
    """Similar trade result"""
    trade_id: str
    similarity_score: float
    trade_data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'trade_id': self.trade_id,
            'similarity_score': round(self.similarity_score, 3),
            'trade_data': self.trade_data
        }

class VectorMemoryStore:
    """
    Vector-based semantic memory
    
    Uses ChromaDB + OpenAI embeddings for:
    - Similar trade retrieval
    - Pattern matching
    - Experience-based learning
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        persist_directory: str = "./chroma_db"
    ):
        # Initialize ChromaDB
        # Note: Settings might vary by version, using simple client init
        try:
            self.client = chromadb.PersistentClient(path=persist_directory)
        except AttributeError:
            # Fallback for older versions
            self.client = chromadb.Client(Settings(
                persist_directory=persist_directory,
                anonymized_telemetry=False
            ))
        
        # Create or get collection.
        # Explicitly pin the distance metric to cosine via `hnsw:space`.
        # Without this, ChromaDB defaults to L2 (squared euclidean), which
        # breaks the distance->similarity mapping below. OpenAI embeddings are
        # unit-normalized, so cosine is the correct metric.
        self.collection = self.client.get_or_create_collection(
            name="trade_memory",
            metadata={
                "description": "Trade history with embeddings",
                "hnsw:space": "cosine",
            }
        )
        
        # OpenAI client for embeddings
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("No OpenAI API key provided. Vector memory will fail on embedding generation.")
        
        self.openai_client = OpenAI(api_key=api_key)
        
        logger.info(f"Vector memory store initialized: {persist_directory}")
    
    def _create_trade_description(self, trade_data: Dict[str, Any]) -> str:
        """Create text description of trade for embedding"""
        
        desc = f"""
        Trade Setup:
        Symbol: {trade_data.get('symbol')}
        Direction: {trade_data.get('direction')}
        Strategy: {trade_data.get('strategy_type')}
        
        Market Conditions:
        Regime: {trade_data.get('market_regime')}
        Volatility: {trade_data.get('volatility_percentile', 'unknown')}
        
        Setup Quality:
        Confidence: {trade_data.get('confidence_score')}
        Confluences: {trade_data.get('confluence_count')}
        SMC Patterns: {', '.join(trade_data.get('smc_patterns', []))}
        ICT Setups: {', '.join(trade_data.get('ict_setups', []))}
        
        Outcome:
        Result: {'WIN' if trade_data.get('is_winner') else 'LOSS'}
        P&L: {trade_data.get('pnl', 0):.2f}
        RR Ratio: {trade_data.get('risk_reward_ratio', 0):.2f}
        """
        
        return desc.strip()
    
    @retry(
        stop=stop_after_attempt(EMBEDDING_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True,
    )
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI.

        Applies a per-request timeout and retries transient failures with
        exponential backoff. After exhausting retries the final exception is
        re-raised so callers can degrade gracefully.
        """
        # `with_options(timeout=...)` bounds each individual request so a hung
        # connection can't stall trade persistence; retry handles transients.
        client = self.openai_client.with_options(timeout=EMBEDDING_TIMEOUT_SECONDS)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    
    def store_trade(
        self,
        trade_id: str,
        trade_data: Dict[str, Any]
    ) -> bool:
        """Store trade in vector memory.

        Vector memory is a best-effort, secondary store used for similarity
        search. A failure here (e.g. embedding API outage) must NOT crash the
        authoritative trade persistence path, so this method logs and returns
        ``False`` on failure instead of raising. Returns ``True`` on success.
        """

        try:
            # Create description
            description = self._create_trade_description(trade_data)
            
            # Generate embedding
            embedding = self._generate_embedding(description)
            
            # Store in ChromaDB
            # ChromaDB expects metadata values to be str, int, float, bool
            # We need to flatten or stringify complex types in metadata
            flat_metadata = {}
            for k, v in trade_data.items():
                if isinstance(v, (str, int, float, bool)):
                    flat_metadata[k] = v
                elif v is None:
                    flat_metadata[k] = ""
                else:
                    flat_metadata[k] = str(v)
            
            # Use upsert (not add) so re-storing an existing trade_id UPDATES the
            # record in place instead of raising a duplicate-id error. This is
            # what makes the learning loop work: a trade is first stored at entry
            # (setup context only) and then re-stored at close with its outcome
            # (win/loss, P&L, RR) merged in.
            self.collection.upsert(
                ids=[trade_id],
                embeddings=[embedding],
                metadatas=[flat_metadata],
                documents=[description]
            )

            logger.debug(f"Trade stored in vector memory: {trade_id}")
            return True

        except Exception as e:
            # Degrade gracefully: vector memory is non-critical, do not let its
            # failure abort the caller's (already-completed) primary persistence.
            logger.error(
                f"Failed to store trade in vector memory (non-fatal, "
                f"trade_id={trade_id}): {e}"
            )
            return False
    
    def find_similar_trades(
        self,
        current_setup: Dict[str, Any],
        n_results: int = 5,
        min_similarity: float = 0.0  # cosine similarity threshold (1 - chroma cosine distance)
    ) -> List[SimilarTrade]:
        """Find similar historical trades"""
        
        try:
            # Create description of current setup
            description = self._create_trade_description(current_setup)
            
            # Generate embedding
            embedding = self._generate_embedding(description)
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                include=['metadatas', 'distances', 'documents']
            )
            
            similar_trades = []
            
            if not results['ids']:
                return []
                
            ids = results['ids'][0]
            distances = results['distances'][0]
            metadatas = results['metadatas'][0]
            
            for i, trade_id in enumerate(ids):
                # The collection is configured with cosine distance
                # (hnsw:space="cosine"), so similarity = 1 - distance.
                distance = distances[i]
                similarity = cosine_distance_to_similarity(distance)

                if similarity >= min_similarity:
                    similar_trades.append(SimilarTrade(
                        trade_id=trade_id,
                        similarity_score=similarity,
                        trade_data=metadatas[i]
                    ))
            
            return similar_trades
            
        except Exception as e:
            logger.error(f"Failed to find similar trades: {e}")
            return []
