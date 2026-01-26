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
import os

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
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name="trade_memory",
            metadata={"description": "Trade history with embeddings"}
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
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    def store_trade(
        self,
        trade_id: str,
        trade_data: Dict[str, Any]
    ):
        """Store trade in vector memory"""
        
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
            
            self.collection.add(
                ids=[trade_id],
                embeddings=[embedding],
                metadatas=[flat_metadata],
                documents=[description]
            )
            
            logger.debug(f"Trade stored in vector memory: {trade_id}")
            
        except Exception as e:
            logger.error(f"Failed to store trade in vector memory: {e}")
            raise
    
    def find_similar_trades(
        self,
        current_setup: Dict[str, Any],
        n_results: int = 5,
        min_similarity: float = 0.0  # Chroma returns distance, not similarity directly usually, but let's assume we handle it
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
                # Convert distance to similarity score (approximate)
                # Cosine distance is 0 to 2. 0 is identical.
                # Similarity = 1 - (distance / 2) ? Or just 1 - distance if normalized?
                # OpenAI embeddings are normalized, so dot product is cosine similarity.
                # Chroma default is L2? Or Cosine?
                # Assuming L2 for now.
                distance = distances[i]
                similarity = 1.0 / (1.0 + distance) # Simple conversion
                
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
