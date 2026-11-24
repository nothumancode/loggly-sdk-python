# Loggly SDK for Python

Search Loggly events, page through results, query statistics and submit logs from Python or the command line. The SDK runs on Python 3.9+ and uses only the standard library. It shares its commands and API schemas with the shell, Lua and Nushell SDKs.

## Installation

Install the PyPI distribution in a virtual environment:

```sh
python -m pip install loggly-sdk
loggly version
```

The distribution provides the `loggly` command and the `loggly` Python module. The older PyPI project named `loggly` also uses that import name. Use separate environments if you need both projects.

From a source checkout, install with `python -m pip install .` or run `python3 loggly.py` directly.

## Start

Inject `LOGGLY_API_TOKEN` and `LOGGLY_SUBDOMAIN` into the environment. The subdomain is the account label, not a URL. Every API call requires both variables. Ingestion additionally needs `LOGGLY_CUSTOMER_TOKEN`; pass `-` in the token argument to read it from the environment.

```sh
loggly doctor
loggly --dry-run count 'q=error' from=-1h
loggly count 'q=error' from=-1h
loggly iterate 'q=tag:production AND error' from=-1h size=20
```

`doctor` checks configuration locally and reports booleans, never credentials. `--dry-run` validates an API invocation and prints its method, endpoint template and query names. It sends no network request and does not read stdin. It omits hosts, credential values, query values and payloads.

## Discover and complete commands

```sh
loggly help
loggly help iterate
loggly tools
loggly schema iterate
loggly examples iterate
loggly version
loggly man
loggly skill list
loggly skill show
loggly skill show references/api.md
loggly completion bash
```

These commands work offline. `tools` returns all 15 API tool definitions as JSON. Each definition contains an input schema, output schema, invocation mapping and side effects. `skill show` reads only embedded allowlisted resources. It cannot read arbitrary local paths. Examples are printed, never executed.

For Bash completion in the current shell:

```bash
source <(loggly completion bash)
```

Completion scripts are also available for `zsh`, `fish` and `nu`. Generate one with `loggly completion SHELL` and load it through the shell's normal configuration. Completion only suggests local metadata. It never fetches logs or exposes credentials.

Run `loggly skill list` to find investigation examples, operation examples, the API reference and invocation guidance. Read any listed file with `loggly skill show RESOURCE`.

## Use the native Python API

```python
import loggly

try:
    result = loggly.call_json("count", "q=error", "from=-1h", timeout=30)
    print(result["count"])
except loggly.Error as error:
    print(error.as_dict())
```

`call` returns unchanged bytes. Use it for JSON, CSV, raw text, GIF data or response headers. `call_json` parses a JSON response and fails if the response is invalid JSON.

```python
import json
import loggly

# Structured input uses the published tool schema and x-cli mapping.
raw = loggly.call_tool("count", {"q": "error", "include_volume": True})
print(json.loads(raw))

# Bound pagination. A remaining cursor after the limit raises an error.
for page in loggly.iter_pages("q=error", "from=-1h", max_pages=5):
    for event in page["events"]:
        print(event)

catalog = loggly.tools()              # fresh dict
contract = loggly.schema("count")     # fresh dict
instructions = loggly.skill()        # Markdown text
```

Use fixed UTC `from` and `until` values when comparing multiple calls or reproducing an investigation. `iter_pages` detects repeated cursors. It does not retry, restart an expired cursor or treat capped retrieval as complete.

For an authorized log submission:

```python
loggly.call("send", "-", "app,production", "application/json",
            body=b'{"message":"approved test event"}')
```

## Validation and failure handling

- Known parameters are checked for required values, scalar duplicates, types, enums and documented limits. Repeatable list parameters remain repeatable. New safe query keys pass through to the service.
- Tags must start with a letter or digit. They can then contain letters, digits, dot, underscore or hyphen. Each tag has at most 64 characters. A lone `-` means no tags.
- Generic paths cannot change host, contain dot traversal, or contain ambiguous escaping. Pagination must use the exact account's iterator route.
- Every HTTP response outside 200–299 fails with exit 22. Redirects are refused. Error bodies and URLs are excluded from diagnostics.
- `Error` exposes `code`, `http_status`, `retry_after` and `retryable`. A retry hint never causes an automatic retry. Pixel GETs and generic requests never receive automatic safe-read classification.
- Exit 2 indicates local validation failure. DNS, TLS, connection and timeout failures use curl-like codes where possible. These are not identical to every curl diagnostic.

The Python API's timeout is a positive **socket I/O timeout**, default 120 seconds. It is not an overall wall-clock deadline. Bodies and responses are buffered in memory. HEAD output reconstructs headers rather than preserving their exact wire formatting. HTTPS uses normal certificate verification and standard proxy/trust environment settings.

## Tests

```sh
python3 tests/test_unit.py
# Development-only: jsonschema and openssl are needed for HTTPS/schema fixtures.
python3 tests/test_contract.py
```

Tests exercise local fixtures only. They do not use a live Loggly account. Vendor response schemas describe documented examples and are not a guarantee about every account or future service version. See `REVIEW.md` for verification and limits.

## Build a release

From the Python checkout, use a fresh virtual environment and an empty `dist/` directory:

```sh
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

This builds a source archive and a wheel from that archive. Both use the version reported by `loggly version`. After verifying the release, a PyPI maintainer can publish those two files with `python -m twine upload dist/*`.
