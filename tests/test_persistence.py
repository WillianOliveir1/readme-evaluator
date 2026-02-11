"""Tests for backend.db.persistence — MongoDB is mocked, file ops use tmp_path."""
from __future__ import annotations

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from backend.db.persistence import save_to_file, save_to_mongo, save_with_mongo_fallback


# =====================================================================
# save_to_file
# =====================================================================

class TestSaveToFile:
    """Test local file persistence."""

    def test_creates_file(self, tmp_path):
        fpath = str(tmp_path / "out.jsonl")
        result = save_to_file({"key": "value"}, fpath)
        assert result == fpath
        assert os.path.exists(fpath)

    def test_appends_to_existing(self, tmp_path):
        fpath = str(tmp_path / "out.jsonl")
        save_to_file({"first": 1}, fpath)
        save_to_file({"second": 2}, fpath)

        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_valid_json_per_line(self, tmp_path):
        fpath = str(tmp_path / "out.jsonl")
        save_to_file({"data": "test"}, fpath)

        with open(fpath, "r", encoding="utf-8") as f:
            line = f.readline()
        obj = json.loads(line)
        assert "document" in obj
        assert obj["document"]["data"] == "test"

    def test_entry_has_id(self, tmp_path):
        fpath = str(tmp_path / "out.jsonl")
        save_to_file({"x": 1}, fpath)

        with open(fpath, "r", encoding="utf-8") as f:
            obj = json.loads(f.readline())
        assert "_id" in obj


# =====================================================================
# save_to_mongo — pymongo is imported locally inside save_to_mongo,
# so we patch it at the pymongo module level.
# =====================================================================

class TestSaveToMongo:
    """Test MongoDB persistence with mocked pymongo."""

    @patch("pymongo.MongoClient")
    def test_inserts_document(self, MockClient):
        mock_coll = MagicMock()
        mock_coll.insert_one.return_value = MagicMock(inserted_id="abc123")
        MockClient.return_value.__getitem__.return_value.__getitem__.return_value = mock_coll
        MockClient.return_value.admin.command.return_value = True

        result = save_to_mongo({"key": "val"}, "mongodb://fake", "db", "coll")
        assert result == "abc123"
        mock_coll.insert_one.assert_called_once()

    @patch("pymongo.MongoClient")
    def test_adds_saved_at_metadata(self, MockClient):
        mock_coll = MagicMock()
        mock_coll.insert_one.return_value = MagicMock(inserted_id="x")
        MockClient.return_value.__getitem__.return_value.__getitem__.return_value = mock_coll
        MockClient.return_value.admin.command.return_value = True

        save_to_mongo({"key": "val"}, "mongodb://fake", "db", "coll")
        call_args = mock_coll.insert_one.call_args[0][0]
        assert "_saved_at" in call_args

    def test_returns_none_when_no_uri(self):
        result = save_to_mongo({"key": "val"}, "", "db", "coll")
        assert result is None

    def test_returns_none_when_uri_none(self):
        result = save_to_mongo({"key": "val"}, None, "db", "coll")
        assert result is None

    @patch("pymongo.MongoClient")
    def test_returns_none_on_connection_failure(self, MockClient):
        from pymongo.errors import ConnectionFailure
        MockClient.return_value.admin.command.side_effect = ConnectionFailure("timeout")

        result = save_to_mongo({"key": "val"}, "mongodb://fake", "db", "coll")
        assert result is None


# =====================================================================
# save_with_mongo_fallback
# =====================================================================

class TestSaveWithFallback:
    """Test combined MongoDB + file persistence."""

    @patch("backend.db.persistence.save_to_mongo")
    def test_saves_to_both(self, mock_mongo, tmp_path):
        mock_mongo.return_value = "mongo_id_123"
        fpath = str(tmp_path / "fallback.jsonl")

        mongo_id, file_path = save_with_mongo_fallback(
            {"data": 1}, fpath, mongo_uri="mongodb://fake"
        )
        assert mongo_id == "mongo_id_123"
        assert file_path == fpath
        assert os.path.exists(fpath)

    @patch("backend.db.persistence.save_to_mongo")
    def test_file_saved_even_when_mongo_fails(self, mock_mongo, tmp_path):
        mock_mongo.return_value = None  # MongoDB failed
        fpath = str(tmp_path / "fallback.jsonl")

        mongo_id, file_path = save_with_mongo_fallback(
            {"data": 1}, fpath, mongo_uri="mongodb://fake"
        )
        assert mongo_id is None
        assert os.path.exists(fpath)

    def test_file_saved_when_no_mongo_uri(self, tmp_path):
        fpath = str(tmp_path / "fallback.jsonl")

        mongo_id, file_path = save_with_mongo_fallback(
            {"data": 1}, fpath, mongo_uri=None
        )
        assert mongo_id is None
        assert os.path.exists(fpath)
