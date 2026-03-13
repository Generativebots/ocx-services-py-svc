"""Tests for authority service modules"""
import pytest
from unittest.mock import patch, MagicMock
from enum import Enum

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from advanced_impact_estimator import Industry, ImpactAssumptions, AdvancedImpactEstimator
from impact_estimator import BusinessImpactEstimator
from mock_scanner import MockScanner
from use_case_generator import A2APattern, A2AUseCaseGenerator


# All classes need a db_conn mock
def _mock_db():
    db = MagicMock()
    db.table.return_value.select.return_value.execute.return_value.data = []
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "test"}]
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return db


class TestIndustry:
    def test_is_enum(self):
        assert issubclass(Industry, Enum)

    def test_has_values(self):
        assert len(list(Industry)) > 0


class TestAdvancedImpactEstimator:
    def test_init(self):
        e = AdvancedImpactEstimator(_mock_db())
        assert e is not None


class TestBusinessImpactEstimator:
    def test_init(self):
        e = BusinessImpactEstimator(_mock_db())
        assert e is not None


class TestMockScanner:
    def test_init(self):
        s = MockScanner(_mock_db())
        assert s is not None

    def test_scan_returns_results(self):
        s = MockScanner(_mock_db())
        result = s.scan_document(
            tenant_id="acme",
            doc_type="regulatory",
            file_path="/tmp/test.pdf",
            file_content="Sample document text about financial compliance",
        )
        assert isinstance(result, dict)

    def test_scan_empty_text(self):
        s = MockScanner(_mock_db())
        result = s.scan_document("acme", "regulatory", "/tmp/test.pdf", "")
        assert result is not None


class TestA2APattern:
    def test_is_enum(self):
        assert issubclass(A2APattern, Enum)


class TestA2AUseCaseGenerator:
    def test_init(self):
        g = A2AUseCaseGenerator(_mock_db())
        assert g is not None
