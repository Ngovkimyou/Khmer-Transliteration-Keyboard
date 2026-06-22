"""Local named-pipe suggestion engine for the Windows IME prototype.

Protocol:
    client -> server: one UTF-8 JSON object ending with "\n"
    server -> client: one UTF-8 JSON object ending with "\n"

Example request:
    {"q":"som","limit":20}

Example response:
    {"ok":true,"query":"som","normalized":"som","suggestions":[...]}
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from khmer_transliteration.dictionary_lookup import load_dataset
from khmer_transliteration.history import record_selection
from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.normalizer import normalize_phrase_input
from khmer_transliteration.suggestion_engine import get_suggestions, load_ranking_model


PIPE_NAME = r"\\.\pipe\KhmerRomanizedIme"
BUFFER_SIZE = 64 * 1024

# Minimal Win32 named-pipe bindings. Keeping this in-process avoids an HTTP
# server/port and keeps IME requests local to the machine.
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_PIPE_CONNECTED = 535

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreateNamedPipeW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
]
kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL

kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
kernel32.ReadFile.restype = wintypes.BOOL

kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
kernel32.WriteFile.restype = wintypes.BOOL

kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
kernel32.FlushFileBuffers.restype = wintypes.BOOL

kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
kernel32.DisconnectNamedPipe.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class EngineState:
    """Keeps expensive dictionary/model data warm in memory."""

    def __init__(self) -> None:
        self.dataset = load_dataset()
        self.rules = load_mapping_rules()
        self.ranking_model = load_ranking_model()

    def handle_request(self, request: dict) -> dict:
        """Route one client request by action name."""
        action = str(request.get("action", "suggest"))

        if action == "select":
            return self.record_selection(request)

        return self.suggest(request)

    def record_selection(self, request: dict) -> dict:
        """Persist a clicked/committed candidate for personalization."""
        query = str(request.get("q", ""))
        khmer = str(request.get("khmer", ""))
        previous_word = str(request.get("previous_word", ""))
        counts = record_selection(query, khmer, previous_khmer=previous_word)

        return {
            "ok": True,
            "action": "select",
            "query": query,
            "khmer": khmer,
            "previous_word": previous_word,
            **counts,
        }

    def suggest(self, request: dict) -> dict:
        """Generate ranked Khmer suggestions using the already-loaded engine."""
        query = str(request.get("q", ""))
        limit = int(request.get("limit", 20) or 20)
        allow_vowels = bool(request.get("allow_vowels", False))
        previous_word = str(request.get("previous_word", ""))
        normalized = normalize_phrase_input(query)

        if not normalized:
            return {
                "ok": True,
                "query": query,
                "normalized": normalized,
                "suggestions": [],
            }

        suggestions = get_suggestions(
            query,
            dataset=self.dataset,
            rules=self.rules,
            ranking_model=self.ranking_model,
            allow_vowels=allow_vowels,
            previous_word=previous_word,
            limit=limit,
            min_rule_score=None,
        )

        return {
            "ok": True,
            "query": query,
            "normalized": normalized,
            "suggestions": suggestions,
        }


def last_error() -> int:
    return ctypes.get_last_error()


def raise_windows_error(action: str) -> None:
    raise OSError(last_error(), f"{action} failed")


def create_pipe() -> wintypes.HANDLE:
    """Create one server-side pipe instance for a single request/response."""
    pipe = kernel32.CreateNamedPipeW(
        PIPE_NAME,
        PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
        PIPE_UNLIMITED_INSTANCES,
        BUFFER_SIZE,
        BUFFER_SIZE,
        0,
        None,
    )

    if pipe == INVALID_HANDLE_VALUE:
        raise_windows_error("CreateNamedPipeW")

    return pipe


def read_request(pipe: wintypes.HANDLE) -> dict:
    """Read one newline-terminated UTF-8 JSON request from the pipe."""
    chunks: list[bytes] = []

    while True:
        buffer = ctypes.create_string_buffer(4096)
        bytes_read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(
            pipe,
            buffer,
            len(buffer),
            ctypes.byref(bytes_read),
            None,
        )

        if not ok:
            raise_windows_error("ReadFile")

        if bytes_read.value == 0:
            break

        chunk = buffer.raw[: bytes_read.value]
        chunks.append(chunk)

        if b"\n" in chunk:
            break

    raw = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
    return json.loads(raw)


def write_response(pipe: wintypes.HANDLE, response: dict) -> None:
    """Write one compact UTF-8 JSON response and flush it to the client."""
    payload = (
        json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    bytes_written = wintypes.DWORD(0)
    ok = kernel32.WriteFile(
        pipe,
        payload,
        len(payload),
        ctypes.byref(bytes_written),
        None,
    )

    if not ok:
        raise_windows_error("WriteFile")

    kernel32.FlushFileBuffers(pipe)


def handle_client(pipe: wintypes.HANDLE, engine: EngineState) -> None:
    """Handle one connected IME client without letting bad input stop the server."""
    try:
        request = read_request(pipe)
        response = engine.handle_request(request)
    except Exception as exc:  # Keep the engine alive even for malformed requests.
        response = {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "suggestions": [],
        }

    write_response(pipe, response)


def serve(once: bool = False) -> None:
    """Run the pipe loop. The engine object is reused so data stays warm."""
    engine = EngineState()
    print(f"Khmer pipe engine ready: {PIPE_NAME}", flush=True)

    while True:
        pipe = create_pipe()

        try:
            connected = kernel32.ConnectNamedPipe(pipe, None)
            if not connected and last_error() != ERROR_PIPE_CONNECTED:
                raise_windows_error("ConnectNamedPipe")

            handle_client(pipe, engine)
        finally:
            kernel32.DisconnectNamedPipe(pipe)
            kernel32.CloseHandle(pipe)

        if once:
            break


def main() -> int:
    """CLI entry point used by start_pipe_engine.cmd and smoke tests."""
    parser = argparse.ArgumentParser(description="Run Khmer IME named-pipe engine.")
    parser.add_argument("--once", action="store_true", help="Handle one request, then exit.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    serve(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
