# Loggly API reference

Use `loggly schema COMMAND` for the exact machine-readable input and output contract. The SDK exposes these 15 API operations; `help`, `tools`, `schema`, `man`, `version`, `doctor`, `examples`, `completion`, and `skill` are local discovery commands rather than API calls.

| Command | HTTP route | Notes |
|---|---|---|
| `search` | GET `/apiv2/search` | Requires `q`; returns a search ID |
| `events` | GET `/apiv2/events` | Requires `rsid`; JSON, raw or CSV |
| `iterate` | GET `/apiv2/events/iterate` | Preferred event retrieval; up to 1,000 events per page |
| `next` | GET returned iterator URL | Same account only; 10-minute idle cursor expiry |
| `count` | GET `/apiv2/events/count` | Optional `include_volume=true` for byte volume |
| `fields` | GET `/apiv2/fields/` | Discover indexed fields; documented maximum 500 |
| `field` | GET `/apiv2/fields/{field}/` | Field values and counts; documented maximum 300 |
| `stats` | GET `/apiv2/stats/{type}/{field}` | Numeric field; eligible Enterprise subscription |
| `usage` | GET `/apiv2/volume-metrics` | Requires `from` and `until`; filters/groupings |
| `customer` | GET `/apiv2/customer` | Sensitive; may return ingestion tokens |
| `users` | GET `/apiv2/user-list` | Sensitive; may return personal data |
| `send` | POST `/inputs/{customer_token}/` | One event; 1 MB documented limit |
| `bulk` | POST `/bulk/{customer_token}/` | Newline-separated events; 5 MB batch, 1 MB per event |
| `pixel` | GET `/inputs/{customer_token}.gif` or tagged route | Writes an event; GIF response |
| `request` | Same-account absolute path | Generic method and route; effect varies |

Read and account operations use the account's HTTPS host. Ingestion uses `https://logs-01.loggly.com` with a separate customer token. The SDK requires `LOGGLY_API_TOKEN` and `LOGGLY_SUBDOMAIN` for every network request, and the ingestion commands additionally require a customer token (use `-` to read `LOGGLY_CUSTOMER_TOKEN`).

Statistics selectors: `avg`, `sum`, `min`, `max`, `percentiles`, `value_count`, `cardinality`, `stats`, `all`, `extended`. Cardinality is an approximate distinct count. Validate the field type and units before interpretation.

Use `q`, `from`, and `until` where the operation supports them. Quote the query as one shell argument. For usage, supply both time bounds; repeat list parameters such as `group_by=host group_by=app`.

Published response examples are not an authoritative JSON Schema. Actual output may vary by account, service version, query, permissions and subscription. The SDK does not auto-paginate or auto-retry.

## Official documentation

- [API overview](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/api-overview.htm)
- [Token authentication](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/token-based-api-authentication.htm)
- [Search, events and fields](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/api-retrieving-data.htm)
- [Iterator pagination](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/paginating-event-retrieval-api.htm)
- [Event counts](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/event-counts.htm)
- [Volume metrics](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/volume_metrics-api.htm)
- [Statistics](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/stats-api.htm)
- [Account and users](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/api-account-info.htm)
- [HTTP ingestion](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/http-endpoint.htm)
- [Bulk ingestion](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/http-bulk-endpoint.htm)
- [Tracking pixel](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/tracking-pixel.htm)
- [Tags](https://documentation.solarwinds.com/en/success_center/loggly/content/admin/tags.htm)

## Tag and error details

Each tag must start with an ASCII letter or digit, contain only letters, digits, dot, underscore or hyphen, and be no longer than 64 characters. Invalid tags may be discarded by the service while the event is still indexed; all SDKs reject them locally.

`users` may return `last_login` as a timestamp string or the literal string `None`. The usage endpoint documents 404 as no data. The overview documents 503 for throttling; do not automatically retry writes. `search` and `events` remain documented but the iterator page marks the old retrieval API deprecated. Prefer `iterate` and disclose service availability uncertainty for legacy calls.
