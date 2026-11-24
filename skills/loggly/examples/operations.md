# Usage, account operations and ingestion

These are independent examples, not a script to execute wholesale. Assume `loggly` is on `PATH` and required credentials are already injected. Do not run write examples without authorization.

## Usage and volume (read-only)

```sh
loggly usage from=2026-01-01T00:00:00Z until=2026-01-02T00:00:00Z measurement_types=count
loggly usage from=2026-01-01T00:00:00Z until=2026-01-02T00:00:00Z group_by=host group_by=app measurement_types=count
loggly count 'q=tag:production' from=-24h include_volume=true
```

Choose the requested period; the fixed dates above are illustrative. Repeat list-valued query parameters as separate arguments. Review `loggly schema usage` for documented groupings, filters and measurement types. Query event byte volume and account usage are distinct metrics.

## Account data (sensitive reads)

Only invoke these when necessary for the user's task:

```sh
loggly customer
loggly users
```

`customer` may return ingestion tokens; `users` may return personal data. Prefer a narrowly scoped answer instead of exposing the full JSON. Do not invoke `customer` just to obtain an ingestion token for an agent; have the user inject it into the environment instead.

## Ingestion (writes)

Confirm that the user has authorized submissions to the target account. A separate `LOGGLY_CUSTOMER_TOKEN` is required in addition to the two standard variables. Use test tags and synthetic data for approved smoke tests; the `-` token argument reads the environment rather than exposing the token in argv.

```sh
printf '%s\n' '{"message":"SDK smoke test","source":"loggly-sdk"}' |
  loggly send - sdk-test application/json
```

For multiline data as one event or a batch of individual events:

```sh
printf '%s\n' 'line one' 'line two' | loggly send - sdk-test text/plain
printf '%s\n' '{"message":"one"}' '{"message":"two"}' |
  loggly bulk - sdk-test,example application/json
```

Use file redirection for existing payloads. Avoid secrets in log messages. `send` treats multiline content as one event; `bulk` treats newline-delimited content as individual events. The documented limits are 1 MB per event and 5 MB per bulk request. Keep batches small and do not retry blindly.

## Tracking pixel (write)

```sh
loggly pixel - --tags sdk-test message=approved-smoke-test > pixel.gif
```

This GET request writes an event. The returned GIF is binary data; do not interpret it as JSON or print it into a terminal. The local file is created or overwritten by the redirection; use a new path when necessary.

## Generic requests

Prefer a named wrapper whenever available. Check the vendor's documentation before using `request` on another route.

```sh
loggly request GET /apiv2/events/count 'q=error' from=-1h
```

The generic command accepts only same-account absolute paths, not arbitrary URLs. GET/HEAD/DELETE may take `key=value` query arguments; POST/PUT/PATCH take JSON stdin and require already percent-encoded query parameters in the path. A generic mutation needs authorization. Even a generic GET can disclose sensitive data or have endpoint-specific side effects.
