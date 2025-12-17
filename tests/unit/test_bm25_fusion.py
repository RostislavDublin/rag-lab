"""
Unit tests for RRF (Reciprocal Rank Fusion).
"""

import pytest
from src.bm25.fusion import reciprocal_rank_fusion


class TestReciprocalRankFusion:
    """Test RRF fusion logic"""
    
    def test_basic_fusion(self):
        """Test basic RRF with two rankings"""
        ranking1 = [
            {'chunk_id': 1, 'score': 0.9},
            {'chunk_id': 2, 'score': 0.8},
            {'chunk_id': 3, 'score': 0.7}
        ]
        
        ranking2 = [
            {'chunk_id': 3, 'score': 0.95},
            {'chunk_id': 1, 'score': 0.85},
            {'chunk_id': 4, 'score': 0.75}
        ]
        
        fused = reciprocal_rank_fusion([ranking1, ranking2])
        
        # Chunk 1 and 3 appear in both rankings, should be ranked higher
        chunk_ids = [item['chunk_id'] for item in fused]
        
        assert chunk_ids[0] in [1, 3]  # Top items from both rankings
        assert len(fused) == 4  # Total unique items
        assert all('rrf_score' in item for item in fused)
    
    def test_rrf_score_calculation(self):
        """Test RRF score calculation formula"""
        ranking = [
            {'chunk_id': 1},
            {'chunk_id': 2}
        ]
        
        fused = reciprocal_rank_fusion([ranking], k=60)
        
        # RRF(chunk_1, k=60) = 1/(60+1) ≈ 0.0164
        # RRF(chunk_2, k=60) = 1/(60+2) ≈ 0.0161
        
        assert fused[0]['chunk_id'] == 1
        assert fused[1]['chunk_id'] == 2
        assert fused[0]['rrf_score'] == pytest.approx(1/61, abs=0.0001)
        assert fused[1]['rrf_score'] == pytest.approx(1/62, abs=0.0001)
    
    def test_overlapping_items(self):
        """Test that overlapping items get boosted"""
        ranking1 = [
            {'chunk_id': 1},
            {'chunk_id': 2},
            {'chunk_id': 3}
        ]
        
        ranking2 = [
            {'chunk_id': 2},  # Rank 1 in second ranking
            {'chunk_id': 4},
            {'chunk_id': 1}   # Rank 3 in second ranking
        ]
        
        fused = reciprocal_rank_fusion([ranking1, ranking2], k=60)
        
        # Chunk 2: rank 2 in first, rank 1 in second → highest RRF
        # Chunk 1: rank 1 in first, rank 3 in second → high RRF
        
        assert fused[0]['chunk_id'] in [1, 2]
        assert fused[0]['rrf_score'] > fused[2]['rrf_score']
    
    def test_empty_rankings(self):
        """Test handling of empty rankings"""
        fused = reciprocal_rank_fusion([])
        assert fused == []
        
        fused = reciprocal_rank_fusion([[]])
        assert fused == []
    
    def test_single_ranking(self):
        """Test RRF with single ranking (passthrough)"""
        ranking = [
            {'chunk_id': 1},
            {'chunk_id': 2},
            {'chunk_id': 3}
        ]
        
        fused = reciprocal_rank_fusion([ranking])
        
        assert len(fused) == 3
        assert [item['chunk_id'] for item in fused] == [1, 2, 3]
    
    def test_custom_item_key(self):
        """Test RRF with custom item key"""
        ranking1 = [
            {'doc_id': 'A'},
            {'doc_id': 'B'}
        ]
        
        ranking2 = [
            {'doc_id': 'B'},
            {'doc_id': 'C'}
        ]
        
        fused = reciprocal_rank_fusion(
            [ranking1, ranking2],
            item_key='doc_id'
        )
        
        assert fused[0]['doc_id'] == 'B'  # Appears in both
        assert len(fused) == 3
    
    def test_rrf_constant_k(self):
        """Test effect of different k values"""
        ranking = [
            {'chunk_id': 1},
            {'chunk_id': 2}
        ]
        
        fused_k60 = reciprocal_rank_fusion([ranking], k=60)
        fused_k10 = reciprocal_rank_fusion([ranking], k=10)
        
        # Lower k = higher scores
        assert fused_k10[0]['rrf_score'] > fused_k60[0]['rrf_score']
    
    def test_preserves_original_data(self):
        """Test that original item data is preserved"""
        ranking1 = [
            {'chunk_id': 1, 'similarity': 0.9, 'doc_uuid': 'abc'},
            {'chunk_id': 2, 'similarity': 0.8, 'doc_uuid': 'def'}
        ]
        
        fused = reciprocal_rank_fusion([ranking1])
        
        assert fused[0]['similarity'] == 0.9
        assert fused[0]['doc_uuid'] == 'abc'
        assert 'rrf_score' in fused[0]
    
    def test_three_way_fusion(self):
        """Test RRF with three rankings"""
        ranking1 = [{'chunk_id': 1}, {'chunk_id': 2}]
        ranking2 = [{'chunk_id': 2}, {'chunk_id': 3}]
        ranking3 = [{'chunk_id': 1}, {'chunk_id': 2}, {'chunk_id': 4}]
        
        fused = reciprocal_rank_fusion([ranking1, ranking2, ranking3])
        
        # Chunk 2 appears in all three rankings
        assert fused[0]['chunk_id'] == 2
        assert len(fused) == 4  # Unique items: 1, 2, 3, 4
