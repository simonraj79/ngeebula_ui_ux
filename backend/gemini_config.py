"""Load a Gemini credential without exposing it through the API or logs."""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values
from google import genai
from google.genai import types


DEFAULT_MODEL_NAME = "gemini-3.8-flash"
# Compatibility for callers that only need the documented default. Runtime
# requests use get_model_name()/resolve_configuration() so .env edits are live.
MODEL_NAME = DEFAULT_MODEL_NAME
REQUEST_TIMEOUT_MS = 20_000


@dataclass(frozen=True)
class GeminiCredential:
    value: str = field(repr=False)
    source: str


@dataclass(frozen=True)
class GeminiConfiguration:
    credential: Optional[GeminiCredential]
    model: str


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def credential_path() -> Path:
    override = os.getenv("NGEEBULA_GEMINI_KEY_FILE")
    if override:
        return Path(override).expanduser()
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Ngeebula" / "gemini-key.dpapi"
    return Path.home() / "AppData" / "Local" / "Ngeebula" / "gemini-key.dpapi"


def env_file_path() -> Path:
    override = os.getenv("NGEEBULA_ENV_FILE")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent / ".env"


def _dotenv_settings() -> Dict[str, str]:
    """Read a fresh .env snapshot without copying values into os.environ."""
    try:
        values = dotenv_values(env_file_path(), interpolate=False, encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    return {key: value for key, value in values.items()
            if isinstance(key, str) and isinstance(value, str)}


def _decrypt_windows_dpapi(encoded: bytes) -> str:
    if os.name != "nt":
        raise OSError("Windows DPAPI is available only on Windows")
    encrypted = base64.b64decode(encoded.strip(), validate=True)
    if not encrypted:
        raise ValueError("The credential file is empty")
    buffer = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
    input_blob = _DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 0,
                                      ctypes.byref(output_blob)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        plaintext = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        value = plaintext.decode("utf-8").strip()
        if not value:
            raise ValueError("The decrypted credential is empty")
        return value
    finally:
        if output_blob.pbData:
            ctypes.memset(output_blob.pbData, 0, output_blob.cbData)
            kernel32.LocalFree(output_blob.pbData)


def resolve_configuration() -> GeminiConfiguration:
    """Resolve a fresh environment/.env/DPAPI snapshot without leaking values."""
    dotenv = _dotenv_settings()
    environment = os.getenv("GEMINI_API_KEY", "").strip()
    if environment:
        credential = GeminiCredential(environment, "environment")
    else:
        dotenv_key = dotenv.get("GEMINI_API_KEY", "").strip()
        if dotenv_key:
            credential = GeminiCredential(dotenv_key, "dotenv")
        else:
            try:
                credential = GeminiCredential(
                    _decrypt_windows_dpapi(credential_path().read_bytes()), "secure_store"
                )
            except (OSError, ValueError, UnicodeError, ctypes.ArgumentError):
                credential = None

    environment_model = os.getenv("GEMINI_MODEL", "").strip()
    dotenv_model = dotenv.get("GEMINI_MODEL", "").strip()
    model = environment_model or dotenv_model or DEFAULT_MODEL_NAME
    return GeminiConfiguration(credential=credential, model=model)


def get_credential() -> Optional[GeminiCredential]:
    """Return the preferred credential, or None without leaking load errors."""
    return resolve_configuration().credential


def get_model_name() -> str:
    return resolve_configuration().model


def create_client(credential: Optional[GeminiCredential] = None):
    credential = credential or get_credential()
    if credential is None:
        return None
    return genai.Client(
        api_key=credential.value,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def public_status() -> dict:
    configuration = resolve_configuration()
    credential = configuration.credential
    return {
        "configured": credential is not None,
        "source": credential.source if credential else "none",
        "model": configuration.model,
    }
