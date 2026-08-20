"""Unit tests for perfx/knowledge_tool.py"""
import pytest
from perfx.knowledge_tool import read_rules, read_file


class TestReadRules:
    def test_finds_matching_file(self, tmp_path, monkeypatch):
        rules = tmp_path / "rules"
        rules.mkdir()
        (rules / "io-degradation.md").write_text("# IO Degradation\ncheck HLT exits")
        monkeypatch.setattr("perfx.knowledge_tool.RULES_DIR", rules)
        monkeypatch.setattr("perfx.knowledge_tool.METHODOLOGY_DIR", tmp_path / "methodology")

        r = read_rules("io")
        assert r["files_found"] == 1
        assert "HLT" in r["results"][0]["content"]

    def test_no_match_returns_message(self, tmp_path, monkeypatch):
        monkeypatch.setattr("perfx.knowledge_tool.RULES_DIR", tmp_path / "rules")
        monkeypatch.setattr("perfx.knowledge_tool.METHODOLOGY_DIR", tmp_path / "methodology")

        r = read_rules("nonexistent")
        assert "message" in r

    def test_searches_methodology_too(self, tmp_path, monkeypatch):
        rules = tmp_path / "rules"
        methodology = tmp_path / "methodology"
        rules.mkdir(); methodology.mkdir()
        (methodology / "io-troubleshooting.md").write_text("# IO guide\nstep 1")
        monkeypatch.setattr("perfx.knowledge_tool.RULES_DIR", rules)
        monkeypatch.setattr("perfx.knowledge_tool.METHODOLOGY_DIR", methodology)

        r = read_rules("io")
        assert r["files_found"] == 1
        assert r["results"][0]["source"] == "methodology"

    def test_missing_directories_handled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("perfx.knowledge_tool.RULES_DIR", tmp_path / "nonexistent_rules")
        monkeypatch.setattr("perfx.knowledge_tool.METHODOLOGY_DIR", tmp_path / "nonexistent_method")

        r = read_rules("io")
        assert "message" in r


class TestReadFile:
    def test_reads_single_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\n")
        r = read_file(str(f))
        assert r["content"] == "hello world\n"
        assert r["path"] == str(f)

    def test_truncates_long_file(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("\n".join(f"line {i}" for i in range(500)))
        r = read_file(str(f), max_lines=10)
        assert "more lines" in r["content"]

    def test_glob_pattern_multiple_files(self, tmp_path):
        (tmp_path / "state0").mkdir()
        (tmp_path / "state0" / "name").write_text("POLL\n")
        (tmp_path / "state1").mkdir()
        (tmp_path / "state1" / "name").write_text("C1\n")
        r = read_file(str(tmp_path / "state*/name"))
        assert "files" in r
        assert len(r["files"]) == 2

    def test_nonexistent_file_returns_error(self, tmp_path):
        r = read_file(str(tmp_path / "nonexistent.txt"))
        assert "error" in r or ("files" in r and "error" in r.get("files", [{}])[0])

    def test_no_glob_match_returns_error(self, tmp_path):
        r = read_file(str(tmp_path / "*.xyz"))
        assert "error" in r
