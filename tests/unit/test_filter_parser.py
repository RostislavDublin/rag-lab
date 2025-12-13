"""
Unit tests for MongoDB-style filter parser

Tests conversion of MongoDB query language to PostgreSQL WHERE clauses.
"""

import pytest
from src.lib.filter_parser import parse_filters, FilterParseError, validate_filters


class TestSimpleFilters:
    """Test simple equality and comparison operators"""
    
    def test_simple_equality(self):
        """Test simple field equality: {field: value}"""
        filters = {"user_id": "user123"}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->>'user_id' = $1" in where_clause
        assert params == ["user123"]
    
    def test_explicit_eq_operator(self):
        """Test explicit $eq operator: {field: {$eq: value}}"""
        filters = {"status": {"$eq": "approved"}}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->>'status' = $1" in where_clause
        assert params == ["approved"]
    
    def test_not_equals(self):
        """Test $ne operator: {field: {$ne: value}}"""
        filters = {"status": {"$ne": "archived"}}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->>'status' != $1" in where_clause
        assert params == ["archived"]
    
    def test_greater_than(self):
        """Test $gt operator: {field: {$gt: value}}"""
        filters = {"score": {"$gt": 80}}
        where_clause, params = parse_filters(filters)
        
        assert "(d.metadata->>'score')::numeric > $1" in where_clause
        assert params == [80]
    
    def test_greater_than_or_equal(self):
        """Test $gte operator"""
        filters = {"created_at": {"$gte": "2025-01-01"}}
        where_clause, params = parse_filters(filters)
        
        assert "(d.metadata->>'created_at')::numeric >= $1" in where_clause
        assert params == ["2025-01-01"]
    
    def test_less_than(self):
        """Test $lt operator"""
        filters = {"score": {"$lt": 50}}
        where_clause, params = parse_filters(filters)
        
        assert "(d.metadata->>'score')::numeric < $1" in where_clause
        assert params == [50]
    
    def test_multiple_simple_filters(self):
        """Test multiple top-level filters (implicit AND)"""
        filters = {
            "user_id": "user123",
            "status": "approved"
        }
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->>'user_id' = $" in where_clause
        assert "d.metadata->>'status' = $" in where_clause
        assert "AND" in where_clause
        assert "user123" in params
        assert "approved" in params


class TestArrayOperators:
    """Test array operators: $in, $nin, $all"""
    
    def test_in_operator(self):
        """Test $in operator: {field: {$in: [values]}}"""
        filters = {"tags": {"$in": ["finance", "legal"]}}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->'tags' ?| $1" in where_clause
        assert params == [["finance", "legal"]]
    
    def test_nin_operator(self):
        """Test $nin operator (not in)"""
        filters = {"status": {"$nin": ["draft", "deleted"]}}
        where_clause, params = parse_filters(filters)
        
        assert "NOT (d.metadata->'status' ?| $1::text[])" in where_clause
        assert params == [["draft", "deleted"]]
    
    def test_all_operator(self):
        """Test $all operator (array contains all values)"""
        filters = {"tags": {"$all": ["finance", "2025"]}}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata->'tags' ?& $1" in where_clause
        assert params == [["finance", "2025"]]


class TestLogicalOperators:
    """Test logical operators: $and, $or, $not"""
    
    def test_and_operator(self):
        """Test $and operator"""
        filters = {
            "$and": [
                {"user_id": "user123"},
                {"status": "approved"}
            ]
        }
        where_clause, params = parse_filters(filters)
        
        assert "AND" in where_clause
        assert "user123" in params
        assert "approved" in params
    
    def test_or_operator(self):
        """Test $or operator"""
        filters = {
            "$or": [
                {"department": "legal"},
                {"department": "finance"}
            ]
        }
        where_clause, params = parse_filters(filters)
        
        assert "OR" in where_clause
        assert "legal" in params
        assert "finance" in params
    
    def test_not_operator(self):
        """Test $not operator"""
        filters = {
            "$not": {"status": "archived"}
        }
        where_clause, params = parse_filters(filters)
        
        assert "NOT" in where_clause
        assert "archived" in params
    
    def test_complex_and_or_not(self):
        """Test complex nested AND/OR/NOT"""
        filters = {
            "$and": [
                {"user_id": "user123"},
                {
                    "$or": [
                        {"tags": {"$in": ["finance", "legal"]}},
                        {"department": "accounting"}
                    ]
                },
                {
                    "$not": {"status": "archived"}
                }
            ]
        }
        where_clause, params = parse_filters(filters)
        
        assert "AND" in where_clause
        assert "OR" in where_clause
        assert "NOT" in where_clause
        assert "user123" in params
        assert ["finance", "legal"] in params
        assert "accounting" in params
        assert "archived" in params


class TestExistsOperator:
    """Test $exists operator"""
    
    def test_exists_true(self):
        """Test field exists: {field: {$exists: true}}"""
        filters = {"reviewed_by": {"$exists": True}}
        where_clause, params = parse_filters(filters)
        
        assert "d.metadata ? 'reviewed_by'" in where_clause
        assert params == []
    
    def test_exists_false(self):
        """Test field doesn't exist: {field: {$exists: false}}"""
        filters = {"reviewed_by": {"$exists": False}}
        where_clause, params = parse_filters(filters)
        
        assert "NOT (d.metadata ? 'reviewed_by')" in where_clause
        assert params == []


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_filters(self):
        """Test empty filters return TRUE"""
        filters = {}
        where_clause, params = parse_filters(filters)
        
        assert where_clause == "TRUE"
        assert params == []
    
    def test_invalid_and_value(self):
        """Test $and with non-array value raises error"""
        filters = {"$and": {"user_id": "user123"}}  # Should be array
        
        with pytest.raises(FilterParseError, match=r"\$and operator requires array"):
            parse_filters(filters)
    
    def test_invalid_or_value(self):
        """Test $or with non-array value raises error"""
        filters = {"$or": "invalid"}
        
        with pytest.raises(FilterParseError, match=r"\$or operator requires array"):
            parse_filters(filters)
    
    def test_invalid_not_value(self):
        """Test $not with non-dict value raises error"""
        filters = {"$not": ["invalid"]}
        
        with pytest.raises(FilterParseError, match=r"\$not operator requires object"):
            parse_filters(filters)
    
    def test_unsupported_operator(self):
        """Test unsupported operator raises error"""
        filters = {"$invalid": []}
        
        with pytest.raises(FilterParseError, match="Unsupported logical operator"):
            parse_filters(filters)
    
    def test_invalid_in_value(self):
        """Test $in with non-array value raises error"""
        filters = {"tags": {"$in": "not-an-array"}}
        
        with pytest.raises(FilterParseError, match=r"\$in operator requires array"):
            parse_filters(filters)
    
    def test_invalid_exists_value(self):
        """Test $exists with non-boolean value raises error"""
        filters = {"field": {"$exists": "yes"}}
        
        with pytest.raises(FilterParseError, match=r"\$exists operator requires boolean"):
            parse_filters(filters)


class TestValidateFilters:
    """Test filter validation function"""
    
    def test_valid_filters(self):
        """Test validation returns True for valid filters"""
        filters = {"user_id": "user123"}
        is_valid, error = validate_filters(filters)
        
        assert is_valid is True
        assert error is None
    
    def test_invalid_filters(self):
        """Test validation returns False with error message"""
        filters = {"$invalid": []}
        is_valid, error = validate_filters(filters)
        
        assert is_valid is False
        assert "Unsupported logical operator" in error


class TestTableAlias:
    """Test custom table alias support"""
    
    def test_custom_table_alias(self):
        """Test using custom table alias instead of default 'd'"""
        filters = {"user_id": "user123"}
        where_clause, params = parse_filters(filters, table_alias="custom")
        
        assert "custom.metadata->>'user_id' = $1" in where_clause
        assert params == ["user123"]


class TestRealWorldScenarios:
    """Test real-world filter combinations"""
    
    def test_multi_tenant_filter(self):
        """Test typical multi-tenant filter"""
        filters = {
            "user_id": "user123",
            "status": {"$ne": "deleted"}
        }
        where_clause, params = parse_filters(filters)
        
        assert "user_id" in where_clause
        assert "status" in where_clause
        assert "deleted" in params
    
    def test_date_range_filter(self):
        """Test date range filtering"""
        filters = {
            "created_at": {
                "$gte": "2025-01-01",
                "$lt": "2026-01-01"
            }
        }
        where_clause, params = parse_filters(filters)
        
        assert ">=" in where_clause
        assert "<" in where_clause
        assert "2025-01-01" in params
        assert "2026-01-01" in params
    
    def test_complex_business_logic(self):
        """Test complex business logic filter from ROADMAP"""
        filters = {
            "$and": [
                {"user_id": "user123"},
                {
                    "$or": [
                        {"tags": {"$all": ["legal", "reviewed"]}},
                        {"department": "legal"}
                    ]
                },
                {
                    "$not": {
                        "$or": [
                            {"status": "archived"},
                            {"confidentiality": "top-secret"}
                        ]
                    }
                },
                {"created_at": {"$gte": "2025-01-01"}}
            ]
        }
        
        # Should not raise error
        where_clause, params = parse_filters(filters)
        
        assert where_clause is not None
        assert len(params) > 0
        assert "user123" in params
