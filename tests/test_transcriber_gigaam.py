import sys

import pytest


def test_gigaam_raises_runtime_error_when_transformers_missing(monkeypatch):
    """В контейнере transformers не установлен — GigaAMTranscriber должен сообщить
    что нужно `pip install -e ".[gigaam]"`, а не просто упасть с ImportError."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "transformers":
            raise ImportError("No module named 'transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, "transformers", None)

    from molva.transcriber.gigaam import GigaAMTranscriber

    with pytest.raises(RuntimeError, match="molva\\[gigaam\\]"):
        GigaAMTranscriber()
