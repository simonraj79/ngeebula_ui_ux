"""Security and behavior tests for the optional Gemini setup path."""

from __future__ import annotations

import hmac
import importlib
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE_SCRIPT = ROOT / "scripts" / "configure-gemini.ps1"


class FakeGeminiClient:
    def __init__(self, *, text=None, error=None):
        self.text = text
        self.error = error
        self.models = self
        self.calls = []
        self.closed = False

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)

    def close(self):
        self.closed = True


class FakeProviderError(RuntimeError):
    def __init__(self, message, *, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


def patch_configuration(api, monkeypatch, credential, model="gemini-3.8-flash"):
    configuration = api.main.gemini_config.GeminiConfiguration(
        credential=credential, model=model
    )
    monkeypatch.setattr(
        api.main.gemini_config,
        "resolve_configuration",
        lambda: configuration,
    )
    monkeypatch.setattr(api.main.gemini_config, "get_credential", lambda: credential)
    monkeypatch.setattr(api.main.gemini_config, "get_model_name", lambda: model)
    monkeypatch.setattr(
        api.main.gemini_config,
        "public_status",
        lambda: {
            "configured": credential is not None,
            "source": credential.source if credential else "none",
            "model": model,
        },
    )


def database_snapshot(api):
    return {
        "jobs": api.client.get("/jobs/").json(),
        "audit": api.client.get("/audit-logs/").json(),
    }


def assert_redacted(response, *forbidden_values, caplog=None):
    serialized = response.text
    if caplog is not None:
        serialized += caplog.text
    for value in forbidden_values:
        assert value not in serialized


@pytest.mark.parametrize("source", ["environment", "secure_store"])
def test_ai_status_reports_safe_source_without_serializing_credential(api, monkeypatch, source):
    canary = f"secret-status-canary-{source}"
    credential = api.main.gemini_config.GeminiCredential(canary, source)
    patch_configuration(api, monkeypatch, credential)

    response = api.client.get("/ai/status")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "configured": True,
        "source": source,
        "model": api.main.gemini_config.MODEL_NAME,
    }
    assert_redacted(response, canary)


def test_environment_credential_takes_precedence_over_dotenv_and_secure_store(api, monkeypatch, tmp_path):
    environment_canary = "environment-precedence-canary"
    dotenv_path = tmp_path / "precedence.env"
    dotenv_path.write_text("GEMINI_API_KEY=dotenv-lower-priority-canary\n", encoding="utf-8")
    monkeypatch.setenv("NGEEBULA_ENV_FILE", str(dotenv_path))
    monkeypatch.setenv("GEMINI_API_KEY", environment_canary)
    monkeypatch.setattr(
        api.main.gemini_config,
        "_decrypt_windows_dpapi",
        lambda _encoded: (_ for _ in ()).throw(AssertionError("secure store must not be read")),
    )

    credential = api.real_get_credential()

    assert credential is not None
    assert credential.source == "environment"
    assert hmac.compare_digest(credential.value, environment_canary)


def test_dotenv_credential_is_reloaded_on_each_call_and_blank_is_not_configured(
    api, monkeypatch, tmp_path
):
    dotenv_path = tmp_path / "dynamic.env"
    monkeypatch.setenv("NGEEBULA_ENV_FILE", str(dotenv_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    dotenv_path.write_text("GEMINI_API_KEY=first-dotenv-canary\n", encoding="utf-8")

    first = api.real_get_credential()
    dotenv_path.write_text("GEMINI_API_KEY=second-dotenv-canary\n", encoding="utf-8")
    second = api.real_get_credential()
    dotenv_path.write_text("GEMINI_API_KEY=   \n", encoding="utf-8")
    blank = api.real_get_credential()

    assert first is not None and first.source == "dotenv"
    assert hmac.compare_digest(first.value, "first-dotenv-canary")
    assert second is not None and second.source == "dotenv"
    assert hmac.compare_digest(second.value, "second-dotenv-canary")
    assert blank is None


def test_dotenv_does_not_interpolate_credential_values(api, monkeypatch, tmp_path):
    dotenv_path = tmp_path / "literal.env"
    monkeypatch.setenv("NGEEBULA_ENV_FILE", str(dotenv_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("SHOULD_NOT_EXPAND", "expanded-secret")
    dotenv_path.write_text("GEMINI_API_KEY=${SHOULD_NOT_EXPAND}\n", encoding="utf-8")

    credential = api.real_get_credential()

    assert credential is not None and credential.source == "dotenv"
    assert hmac.compare_digest(credential.value, "${SHOULD_NOT_EXPAND}")


def test_model_resolution_is_dynamic_with_environment_precedence_and_new_default(
    api, monkeypatch, tmp_path
):
    dotenv_path = tmp_path / "models.env"
    monkeypatch.setenv("NGEEBULA_ENV_FILE", str(dotenv_path))
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    dotenv_path.write_text("GEMINI_MODEL=dotenv-model-one\n", encoding="utf-8")
    assert api.main.gemini_config.get_model_name() == "dotenv-model-one"

    dotenv_path.write_text("GEMINI_MODEL=dotenv-model-two\n", encoding="utf-8")
    assert api.main.gemini_config.get_model_name() == "dotenv-model-two"
    monkeypatch.setenv("GEMINI_MODEL", "process-model")
    assert api.main.gemini_config.get_model_name() == "process-model"

    monkeypatch.delenv("GEMINI_MODEL")
    dotenv_path.write_text("GEMINI_MODEL=   \n", encoding="utf-8")
    assert api.main.gemini_config.get_model_name() == "gemini-3.8-flash"


def test_ai_test_without_credential_is_truthful_redacted_and_read_only(api, monkeypatch):
    patch_configuration(api, monkeypatch, None)
    before = database_snapshot(api)

    response = api.client.post("/ai/test")

    assert response.status_code == 400, response.text
    assert response.json()["result"] == "not_configured"
    assert "success" not in response.text.casefold()
    assert database_snapshot(api) == before


def test_ai_test_provider_failure_hides_exception_and_is_read_only(api, monkeypatch, caplog):
    credential_canary = "provider-key-canary"
    exception_canary = "raw-provider-exception-canary"
    credential = api.main.gemini_config.GeminiCredential(credential_canary, "secure_store")
    fake = FakeGeminiClient(error=RuntimeError(f"{exception_canary}: {credential_canary}"))
    patch_configuration(api, monkeypatch, credential)
    monkeypatch.setattr(api.main, "get_gemini_client", lambda supplied=None: fake)
    before = database_snapshot(api)

    response = api.client.post("/ai/test")

    assert response.status_code == 502, response.text
    assert response.json()["result"] == "provider_failed"
    assert response.json()["provider_error"] == "provider_failed"
    assert "provider_status" not in response.json()
    assert fake.closed is True
    assert_redacted(response, credential_canary, exception_canary, caplog=caplog)
    assert database_snapshot(api) == before


@pytest.mark.parametrize(
    ("code", "status", "expected_error", "expected_status", "expected_message"),
    [
        (
            429,
            None,
            "quota_or_billing",
            429,
            "Gemini rejected the request because its quota or billing limit was reached. "
            "Check this project in Google AI Studio.",
        ),
        (
            None,
            "RESOURCE_EXHAUSTED",
            "quota_or_billing",
            429,
            "Gemini rejected the request because its quota or billing limit was reached. "
            "Check this project in Google AI Studio.",
        ),
        (
            401,
            None,
            "auth_or_access",
            401,
            "Gemini rejected the API key or project access. Check the key and project "
            "permissions in Google AI Studio.",
        ),
        (
            403,
            None,
            "auth_or_access",
            403,
            "Gemini rejected the API key or project access. Check the key and project "
            "permissions in Google AI Studio.",
        ),
        (
            404,
            None,
            "model_unavailable",
            404,
            "The configured Gemini model was not found or is unavailable to this project. "
            "Check GEMINI_MODEL and project access.",
        ),
    ],
    ids=["code-429", "resource-exhausted", "unauthorized", "forbidden", "model-not-found"],
)
def test_ai_test_maps_allowlisted_provider_failures_without_leaking_raw_error(
    api,
    monkeypatch,
    caplog,
    code,
    status,
    expected_error,
    expected_status,
    expected_message,
):
    credential_canary = "classified-provider-key-canary"
    exception_canary = "classified-raw-provider-payload-canary"
    credential = api.main.gemini_config.GeminiCredential(credential_canary, "dotenv")
    error = FakeProviderError(
        f"{exception_canary}: embedded {credential_canary}", code=code, status=status
    )
    fake = FakeGeminiClient(error=error)
    patch_configuration(api, monkeypatch, credential)
    monkeypatch.setattr(api.main, "get_gemini_client", lambda supplied=None: fake)
    before = database_snapshot(api)

    response = api.client.post("/ai/test")

    assert response.status_code == 502, response.text
    assert response.json() == {
        "result": "provider_failed",
        "provider_error": expected_error,
        "provider_status": expected_status,
        "source": "dotenv",
        "model": "gemini-3.8-flash",
        "message": expected_message,
    }
    assert fake.closed is True
    assert_redacted(response, credential_canary, exception_canary, caplog=caplog)
    assert database_snapshot(api) == before


@pytest.mark.parametrize(
    "provider_text",
    [
        "not JSON",
        "[]",
        '{"category":"not_in_catalog","activity":"Fabricated work"}',
    ],
    ids=["malformed-json", "wrong-shape", "noncatalog-output"],
)
def test_ai_test_invalid_output_reports_validation_fallback_without_writes(
    api, monkeypatch, provider_text
):
    credential_canary = "validation-key-canary"
    credential = api.main.gemini_config.GeminiCredential(credential_canary, "environment")
    fake = FakeGeminiClient(text=provider_text)
    patch_configuration(api, monkeypatch, credential)
    monkeypatch.setattr(api.main, "get_gemini_client", lambda supplied=None: fake)
    before = database_snapshot(api)

    response = api.client.post("/ai/test")

    assert response.status_code == 422, response.text
    assert response.json()["result"] == "validation_fallback"
    assert fake.closed is True
    assert_redacted(response, credential_canary, provider_text)
    assert database_snapshot(api) == before


def test_ai_test_valid_catalog_assessment_succeeds_without_private_data_or_writes(
    api, monkeypatch
):
    credential_canary = "valid-key-canary"
    credential = api.main.gemini_config.GeminiCredential(credential_canary, "secure_store")
    provider_text = (
        '{"category":"track_and_permanent_way","activity":"Rail defect repair",'
        '"activity_type":"Corrective","required_skills":["Track maintenance"],'
        '"priority":"Medium","effort_level":3,"duration_mins":60,"engineers_needed":2}'
    )
    fake = FakeGeminiClient(text=provider_text)
    patch_configuration(api, monkeypatch, credential)
    monkeypatch.setattr(api.main, "get_gemini_client", lambda supplied=None: fake)
    before = database_snapshot(api)

    response = api.client.post("/ai/test")

    assert response.status_code == 200, response.text
    assert response.json()["result"] == "success"
    assert response.json()["assessment"] == {
        "category": "track_and_permanent_way",
        "activity": "Rail defect repair",
        "assessment_source": "gemini-validated",
    }
    assert fake.closed is True
    assert len(fake.calls) == 1
    prompt = str(fake.calls[0]["contents"])
    assert "Synthetic rail inspection connectivity test" in prompt
    for private_value in (
        "Aisha Track Lead",
        "Ben Track Engineer",
        "aisha@example.test",
        "ben@example.test",
        "+65 0000 0101",
        credential_canary,
    ):
        assert private_value not in prompt
    assert_redacted(response, credential_canary)
    assert database_snapshot(api) == before


def test_status_response_and_provider_call_use_one_resolved_dynamic_model(
    api, monkeypatch, tmp_path
):
    dotenv_key = "dynamic-model-key-canary"
    dotenv_path = tmp_path / "provider-model.env"
    dotenv_path.write_text(
        f"GEMINI_API_KEY={dotenv_key}\nGEMINI_MODEL=dotenv-provider-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NGEEBULA_ENV_FILE", str(dotenv_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(api.main.gemini_config, "get_credential", api.real_get_credential)
    provider_text = (
        '{"category":"track_and_permanent_way","activity":"Rail defect repair",'
        '"activity_type":"Corrective","required_skills":["Track maintenance"],'
        '"priority":"Medium","effort_level":3,"duration_mins":60,"engineers_needed":2}'
    )
    fake = FakeGeminiClient(text=provider_text)
    monkeypatch.setattr(api.main, "get_gemini_client", lambda supplied=None: fake)

    status = api.client.get("/ai/status")
    result = api.client.post("/ai/test")

    assert status.status_code == 200, status.text
    assert result.status_code == 200, result.text
    assert status.json()["source"] == result.json()["source"] == "dotenv"
    assert status.json()["model"] == result.json()["model"] == "dotenv-provider-model"
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == "dotenv-provider-model"
    assert_redacted(status, dotenv_key)
    assert_redacted(result, dotenv_key)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is available only on Windows")
def test_powershell_51_dpapi_roundtrip_uses_only_temporary_store(tmp_path, monkeypatch):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell 5.1 is unavailable")

    dummy_value = "unit-test-only-gemini-value-9f6b"
    isolated_local_app_data = tmp_path / "LocalAppData"
    wrapper = tmp_path / "invoke-configure.ps1"
    script_literal = str(CONFIGURE_SCRIPT).replace("'", "''")
    wrapper.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "function Read-Host {\n"
        "  param([string]$Prompt, [switch]$AsSecureString)\n"
        "  $result = [System.Security.SecureString]::new()\n"
        "  foreach ($character in $env:NGEEBULA_TEST_DUMMY.ToCharArray()) {\n"
        "    $result.AppendChar($character)\n"
        "  }\n"
        "  $result.MakeReadOnly()\n"
        "  return $result\n"
        "}\n"
        "try {\n"
        f"  & '{script_literal}'\n"
        "} catch {\n"
        "  [Console]::Error.WriteLine($_.Exception.Message)\n"
        "  exit 1\n"
        "}\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(isolated_local_app_data)
    environment["NGEEBULA_TEST_DUMMY"] = dummy_value

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert dummy_value not in completed.stdout
    assert dummy_value not in completed.stderr
    assert not completed.stderr.strip(), completed.stderr
    credential_file = isolated_local_app_data / "Ngeebula" / "gemini-key.dpapi"
    assert credential_file.is_file()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("NGEEBULA_GEMINI_KEY_FILE", str(credential_file))
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    gemini_config = importlib.import_module("gemini_config")
    credential = gemini_config.get_credential()
    assert credential is not None
    assert credential.source == "secure_store"
    assert hmac.compare_digest(credential.value, dummy_value)
