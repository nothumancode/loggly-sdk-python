# Python SDK v4 review

## Result

The Python implementation now shares generated API metadata, examples, completions, skills and man content with the other SDKs. It remains a standard-library runtime. No Loggly account was accessed during verification.

## Findings fixed

| Finding | Change and practical effect |
|---|---|
| Redirect responses returned success | All non-2xx responses fail with exit 22. No redirect target receives a token. |
| Invalid tags could be silently dropped by Loggly | Validate the documented 1–64 character tag alphabet and alphanumeric first character. |
| Known scalar parameters could repeat or have invalid values | Enforce documented types, enums, bounds and scalar uniqueness. Preserve repeatable arrays and safe future query keys. |
| Generic paths had inconsistent normalization across transports | Reject dot segments, decoded backslashes/control characters, and malformed percent escapes. |
| Generic exception handling hid programming mistakes | Catch explicit HTTP, network and local I/O failures. Return sanitized structured error metadata. |
| No bounded native pagination API | Add `iter_pages` with a page cap, repeated-cursor detection and explicit incomplete-retrieval errors. |
| Structured agent input required hand-written argument mapping | Add `call_tool` using the generated `x-cli` contract, plus `call_json` for JSON responses. |
| Discovery required opening repository files | Embed all allowlisted skill resources, completion scripts and examples. Add offline doctor, version and redacted dry-run. |

This intentionally changes v3 behavior: HTTP 3xx now fails. Known invalid or duplicated scalar query parameters and invalid tag names now fail locally. Existing valid commands remain supported.

## Executed verification

Tested on Linux with Python 3.12.14.

- `tests/test_unit.py`: 11 focused regression tests passed. They cover doctor secrecy, dry-run without stdin/network, tags, query validation, URL normalization, structured inputs, bounded pagination, retry hints, JSON parsing, resource traversal and all new offline discovery commands.
- `tests/test_contract.py`: all 15 operations and all 30 JSON Schemas passed against a loopback HTTPS fixture server. It exercises actual urllib requests, exact binary payloads, repeated and encoded parameters, all statistics selectors, native module calls, HEAD, errors, redirect refusal and TLS verification. API tests run with curl unavailable on PATH.
- Canonical catalog equality passed against `spec/catalog.json` when run within the combined repository. Skill and resource files matched emitted content. `scripts/generate.py --check --only python` passed.

The fixture suite verifies SDK behavior, not live Loggly responses, subscription access or vendor-side guarantees.

## Deliberate limits

- Bodies and responses are buffered in memory.
- The configurable native timeout is a socket I/O timeout, not a wall-clock deadline. DNS resolution and other system behavior may have their own limits.
- HEAD output reconstructs headers; it does not preserve exact wire formatting.
- The CLI returns raw API output. Schemas describe published examples and allow evolving response properties. No runtime JSON Schema dependency is required.
- No automatic retries. A retry hint applies only to named reads; pixel and generic calls are never classified as automatically safe to retry.
- Native macOS/BSD and other Python versions were not executed in this environment. Python 3.9+ is the intended baseline.
