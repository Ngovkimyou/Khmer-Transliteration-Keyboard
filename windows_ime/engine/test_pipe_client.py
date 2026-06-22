"""Small client for testing the Khmer IME named-pipe engine."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from ctypes import wintypes


PIPE_NAME = r"\\.\pipe\KhmerRomanizedIme"
BUFFER_SIZE = 64 * 1024

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
kernel32.WaitNamedPipeW.restype = wintypes.BOOL

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

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

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def last_error() -> int:
    return ctypes.get_last_error()


def raise_windows_error(action: str) -> None:
    raise OSError(last_error(), f"{action} failed")


def open_pipe(timeout_seconds: float) -> wintypes.HANDLE:
    deadline = time.monotonic() + timeout_seconds

    while True:
        kernel32.WaitNamedPipeW(PIPE_NAME, 1000)
        pipe = kernel32.CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        if pipe != INVALID_HANDLE_VALUE:
            return pipe

        if time.monotonic() >= deadline:
            raise_windows_error("CreateFileW")

        time.sleep(0.25)


def request_suggestions(query: str, limit: int, timeout_seconds: float) -> dict:
    pipe = open_pipe(timeout_seconds)

    try:
        payload = (json.dumps({"q": query, "limit": limit}) + "\n").encode("utf-8")
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
    finally:
        kernel32.CloseHandle(pipe)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the Khmer IME named-pipe engine.")
    parser.add_argument("query", help="Romanized input, for example: som")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for the pipe.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    response = request_suggestions(args.query, args.limit, args.timeout)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
