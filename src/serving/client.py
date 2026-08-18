"""Smoke-test client: send one question to the running server and print the answer.

Point it at the server with SERVER_URL (default localhost:8080, e.g. after
`kubectl port-forward`).

Run:  python -m src.serving.client "What is an ETF?"
"""

from __future__ import annotations

import os
import sys

from . import load_serve_cfg
from .payload import build_chat_payload


def ask(question: str) -> str:
    import requests

    cfg = load_serve_cfg()
    base = os.environ.get("SERVER_URL", "http://localhost:8080").rstrip("/")
    payload = build_chat_payload(question, cfg)
    resp = requests.post(f"{base}/v1/chat/completions", json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def main() -> int:
    question = " ".join(sys.argv[1:]) or "What is an ETF versus a mutual fund?"
    print(f"Q: {question}\n")
    print(f"A: {ask(question)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
