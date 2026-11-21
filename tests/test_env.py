import os

from agentguard.mcp_server import load_env_file


def test_env_file_loads_without_overriding_existing(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# c\nAG_TEST_A=1\nAG_TEST_B='two words'\nAG_TEST_C=from_file\n")
    monkeypatch.delenv("AG_TEST_A", raising=False)
    monkeypatch.delenv("AG_TEST_B", raising=False)
    monkeypatch.setenv("AG_TEST_C", "already")
    load_env_file(str(f))
    assert os.environ["AG_TEST_A"] == "1"
    assert os.environ["AG_TEST_B"] == "two words"
    assert os.environ["AG_TEST_C"] == "already"
    for k in ("AG_TEST_A", "AG_TEST_B"):
        monkeypatch.delenv(k, raising=False)
