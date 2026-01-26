"""
Unit tests for Vector Memory Store
"""
import pytest
from unittest.mock import MagicMock, patch
from src.memory.vector_memory import VectorMemoryStore, SimilarTrade

@pytest.fixture
def mock_openai():
    with patch('src.memory.vector_memory.OpenAI') as mock:
        client = MagicMock()
        mock.return_value = client
        
        # Mock embeddings response
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        client.embeddings.create.return_value = response
        
        yield client

@pytest.fixture
def mock_chroma():
    with patch('src.memory.vector_memory.chromadb') as mock:
        client = MagicMock()
        # Handle both Client and PersistentClient calls
        mock.Client.return_value = client
        mock.PersistentClient.return_value = client
        
        collection = MagicMock()
        client.get_or_create_collection.return_value = collection
        
        yield client, collection

def test_store_trade(mock_openai, mock_chroma):
    """Test storing a trade"""
    client, collection = mock_chroma
    
    store = VectorMemoryStore(openai_api_key="fake-key")
    
    trade_data = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'strategy_type': 'SCALP',
        'market_regime': 'trending',
        'is_winner': True,
        'pnl': 100.0
    }
    
    store.store_trade("trade_1", trade_data)
    
    # Verify embedding called
    mock_openai.embeddings.create.assert_called_once()
    
    # Verify chroma add called
    collection.add.assert_called_once()
    call_args = collection.add.call_args[1]
    assert call_args['ids'] == ['trade_1']
    assert call_args['embeddings'] == [[0.1, 0.2, 0.3]]
    assert call_args['metadatas'][0]['symbol'] == 'BTCUSDT'

def test_find_similar_trades(mock_openai, mock_chroma):
    """Test finding similar trades"""
    client, collection = mock_chroma
    
    # Mock query results
    collection.query.return_value = {
        'ids': [['t1', 't2']],
        'distances': [[0.1, 0.5]],
        'metadatas': [[{'symbol': 'BTC'}, {'symbol': 'ETH'}]],
        'documents': [['desc1', 'desc2']]
    }
    
    store = VectorMemoryStore(openai_api_key="fake-key")
    
    current_setup = {'symbol': 'BTCUSDT', 'direction': 'LONG'}
    results = store.find_similar_trades(current_setup)
    
    assert len(results) == 2
    assert results[0].trade_id == 't1'
    assert results[0].trade_data['symbol'] == 'BTC'
    assert results[0].similarity_score > results[1].similarity_score
