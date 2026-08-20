"""Unit tests for perfx/gdrive/gdrive.py"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from perfx.gdrive.gdrive import _extract_id, list_gdrive_folder, read_gdrive, search_gdrive


class TestExtractId:
    def test_plain_id_returned_as_is(self):
        assert _extract_id("abc123XYZ") == "abc123XYZ"

    def test_extracts_from_file_url(self):
        url = "https://drive.google.com/file/d/1abc123XYZ/view"
        assert _extract_id(url) == "1abc123XYZ"

    def test_extracts_from_folder_url(self):
        url = "https://drive.google.com/drive/folders/1folder123"
        assert _extract_id(url, kind="folder") == "1folder123"

    def test_extracts_id_param(self):
        url = "https://docs.google.com/document/d/1docID/edit?id=1docID"
        assert _extract_id(url) == "1docID"


class TestListGdriveFolder:
    def _mock_creds(self, tmp_path, monkeypatch):
        creds = tmp_path / ".gdrive-server-credentials.json"
        creds.write_text(json.dumps({"access_token": "fake-token"}))
        monkeypatch.setattr("perfx.gdrive.gdrive._CREDS_FILE", creds)

    def test_returns_files(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "files": [
                {"id": "1abc", "name": "test.doc", "mimeType": "application/vnd.google-apps.document"},
            ]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = list_gdrive_folder("1folderID")

        assert result["count"] == 1
        assert result["files"][0]["name"] == "test.doc"

    def test_no_creds_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("perfx.gdrive.gdrive._CREDS_FILE", tmp_path / "missing.json")
        result = list_gdrive_folder("1folderID")
        assert "error" in result

    def test_extracts_folder_id_from_url(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"files": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            list_gdrive_folder("https://drive.google.com/drive/folders/1abc123")

        # verify the folder ID was extracted and used in the query
        called_url = mock_open.call_args[0][0].full_url
        assert "1abc123" in called_url


class TestReadGdrive:
    def _mock_creds(self, tmp_path, monkeypatch):
        creds = tmp_path / ".gdrive-server-credentials.json"
        creds.write_text(json.dumps({"access_token": "fake-token"}))
        monkeypatch.setattr("perfx.gdrive.gdrive._CREDS_FILE", creds)

    def test_reads_google_doc(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)

        meta_resp = MagicMock()
        meta_resp.read.return_value = json.dumps({
            "name": "My Doc", "mimeType": "application/vnd.google-apps.document"
        }).encode()
        meta_resp.__enter__ = lambda s: s
        meta_resp.__exit__ = MagicMock(return_value=False)

        content_resp = MagicMock()
        content_resp.read.return_value = b"Hello from Drive"
        content_resp.__enter__ = lambda s: s
        content_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=[meta_resp, content_resp]):
            result = read_gdrive("1docID")

        assert result["name"] == "My Doc"
        assert result["content"] == "Hello from Drive"

    def test_truncates_long_content(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)

        meta_resp = MagicMock()
        meta_resp.read.return_value = json.dumps({
            "name": "Big Doc", "mimeType": "application/vnd.google-apps.document"
        }).encode()
        meta_resp.__enter__ = lambda s: s
        meta_resp.__exit__ = MagicMock(return_value=False)

        content_resp = MagicMock()
        content_resp.read.return_value = ("x" * 10000).encode()
        content_resp.__enter__ = lambda s: s
        content_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=[meta_resp, content_resp]):
            result = read_gdrive("1docID", max_chars=100)

        assert len(result["content"]) == 100
        assert result["truncated"] is True

    def test_no_creds_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("perfx.gdrive.gdrive._CREDS_FILE", tmp_path / "missing.json")
        result = read_gdrive("1docID")
        assert "error" in result


class TestSearchGdrive:
    def _mock_creds(self, tmp_path, monkeypatch):
        creds = tmp_path / ".gdrive-server-credentials.json"
        creds.write_text(json.dumps({"access_token": "fake-token"}))
        monkeypatch.setattr("perfx.gdrive.gdrive._CREDS_FILE", creds)

    def test_returns_search_results(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "files": [{"id": "1x", "name": "sosreport.tar.gz", "mimeType": "application/x-gzip"}]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = search_gdrive("sosreport")

        assert result["count"] == 1
        assert result["files"][0]["name"] == "sosreport.tar.gz"

    def test_empty_results(self, tmp_path, monkeypatch):
        self._mock_creds(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"files": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = search_gdrive("nonexistent")

        assert result["count"] == 0
