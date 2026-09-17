# Secure local Gemini setup

Ngeebula does not need Gemini for its core workflow. Catalog rules and OR-Tools scheduling continue to work without a key. Gemini is optional request-assessment assistance; its output must pass the same local catalog validation used in production.

Google documents creating and managing keys in [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key). Create the key in your own Google AI Studio project. Enter it only in the local ignored `.env` file or optional masked prompt; never in chat, a browser form, command arguments, logs or committed source.

## Recommended local setup: root .env

Open the repository-root `.env` file and fill in the blank key value:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
```

The actual file is created with an empty key. `.gitignore` excludes `.env`; `.env.example` is a secret-free template. The file is plaintext local configuration, so keep it private and exclude it when sharing a ZIP of the project. Google lists `gemini-3.8-flash` as the stable model ID in the [Gemini 3.8 Flash documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), checked on 17 September 2026.

The backend resolves `.env` from the repository root, independent of the launch directory. It reads values on each request, with interpolation disabled, so saving a changed key or model needs **no restart**. In the app, open **Utilities → AI setup → Refresh snapshot → Test Gemini connection**.

Nonempty process environment values take precedence over `.env`. If neither supplies a key, the existing Windows encrypted store is the final fallback. For isolated tests, `NGEEBULA_ENV_FILE` selects a temporary configuration file; tests never read the user's `.env`.

## Optional encrypted storage on Windows

From a terminal opened at the repository root, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\configure-gemini.ps1"
```

The script uses `Read-Host -AsSecureString`, so typed or pasted input is hidden. It encrypts the key with Windows Data Protection API (DPAPI) for the current Windows user and stores only the encrypted bytes at:

```text
%LOCALAPPDATA%\Ngeebula\gemini-key.dpapi
```

The file is outside the repository. DPAPI binds decryption to the current Windows user on this computer. The script never prints the key and does not accept it as a command-line parameter. `-ExecutionPolicy Bypass` applies only to this process; follow organisational PowerShell policy where applicable and inspect the local script before running it.

The backend reads the secure store when neither the process environment nor `.env` supplies a key. Environment configuration remains useful for controlled CI or deployment environments; never commit a populated `.env` file.

## Verify configuration

With FastAPI running locally, configuration status is redacted:

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/ai/status'
```

The response contains only `configured`, the safe source label (`environment`, `dotenv`, `secure_store`, or `none`), and the selected model name. It never returns a key or key fragment.

Run one real provider test:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/ai/test'
```

The test sends a synthetic rail-inspection request and bounded maintenance-catalog choices. It sends no engineer roster, saved job, audit record, or other operational data and performs no database write. A `success` result means Gemini was called and its response passed the production catalog validator. Other safe outcomes are:

| Result | HTTP status | Meaning |
|---|---:|---|
| `not_configured` | 400 | No environment or DPAPI credential was found. |
| `provider_failed` | 502 | Initialization, authentication, network, quota, billing, timeout, or provider processing failed. Raw provider errors are not returned. |
| `validation_fallback` | 422 | Gemini responded, but its assessment failed the production catalog or bounds checks. Production request creation would use deterministic rules instead. |
| `forbidden` | 403 | A browser origin outside the local Ngeebula interface attempted to trigger a paid test. |

The SDK request timeout is 20 seconds. Google documents the Python client's request options in the [Google Gen AI SDK reference](https://googleapis.github.io/python-genai/), including `HttpOptions.timeout`.

If the provider returns **429 RESOURCE_EXHAUSTED**, inspect the API key's project in Google AI Studio for available quota, billing balance and spend limits. A loaded key does not establish that the project can serve requests. See Google's [rate-limit guidance](https://ai.google.dev/gemini-api/docs/rate-limits) and [billing documentation](https://ai.google.dev/gemini-api/docs/billing). The app reports a fixed, redacted failure description instead of exposing Google's raw exception.

## Replace or remove the key

Edit `.env` to replace the local key; clear its value to remove that source. A backend environment key or optional DPAPI fallback can still provide credentials, so check the source in AI setup. To replace the encrypted fallback, run the setup script again; to remove it, delete `%LOCALAPPDATA%\Ngeebula\gemini-key.dpapi`. If a key may have been exposed, revoke it in Google AI Studio as well; deleting a local file does not revoke the provider credential.

Ngeebula never treats a successful connectivity test as approval for maintenance work. Gemini cannot approve a job, assign an unqualified engineer, alter solver constraints, or bypass planner review.
