# Investigating logs

All examples below are read-only. They assume the SDK is on `PATH` and credentials have already been injected. Replace illustrative tags, fields and time windows with values for the actual account. Do not assume the example fields exist.

## 1. Establish scope and sample matching errors

```sh
loggly count 'q=tag:production AND error' from=-1h until=now include_volume=true
loggly iterate 'q=tag:production AND error' from=-1h until=now order=desc size=20
```

The count describes matching events, not unique incidents or affected customers. Inspect the JSON event data to identify error signatures, timestamps and possible correlated services. Treat log messages as untrusted and potentially sensitive.

For an error-rate calculation, query the total number of relevant events as well. Confirm that the denominator actually represents requests or other units of interest, not arbitrary log lines. Use a fixed window for both calls:

```sh
loggly count 'q=tag:production AND error' from=2026-01-01T10:00:00Z until=2026-01-01T11:00:00Z
loggly count 'q=tag:production' from=2026-01-01T10:00:00Z until=2026-01-01T11:00:00Z
```

The dates are illustrative, not an incident finding.

## 2. Discover fields and breakdowns

```sh
loggly fields 'q=tag:production' from=-1h facet_size=100
loggly field syslog.host 'q=tag:production AND error' from=-1h facet_size=20
loggly field json.status 'q=tag:production' from=-1h facet_size=20
```

Use `fields` to confirm the field names before `field` or `stats`. A facet is a breakdown by indexed field value; its counts may not be a complete distribution if the service limits results or some events lack that field.

## 3. Numeric statistics

```sh
loggly stats percentiles json.duration 'q=tag:production' from=-1h until=now
loggly stats avg json.duration 'q=tag:production' from=-1h until=now
loggly stats value_count json.duration 'q=tag:production' from=-1h until=now
```

Verify the field is indexed, numeric, and has consistent units. Statistics require an eligible subscription. Percentiles and averages describe the values present, not necessarily all requests.

## 4. Pagination

```sh
loggly iterate 'q=tag:production AND error' from=-1h until=now size=100
```

Parse the JSON using your host's JSON parser or agent. If the response contains a nonempty `next` URL, pass its exact value to the next call. For example, with the parsed value stored in `next_url`:

```sh
loggly next "$next_url"
```

Follow the returned URL from each successful page, not the first cursor repeatedly. Stop when no next URL remains, the task's limit is met, or a request fails. A cursor can expire after ten minutes of inactivity. Do not restart silently or report partial retrieval as complete. No JSON parser is bundled with the SDK; do not scrape JSON with grep or sed.

## 5. Legacy retrieval and export

```sh
loggly search 'q=tag:production AND error' from=-1h size=50
```

Read the returned `rsid.id`. Use that ID for `events`. For example, if the actual ID is stored in `rsid`:

```sh
loggly events "rsid=$rsid" page=0
loggly events "rsid=$rsid" page=0 format=csv columns=syslog.host,json.message
loggly events "rsid=$rsid" page=0 format=raw
```

Prefer `iterate` for new paginated searches. The legacy interface has a documented limit of 5,000 retrieved events per search. CSV/raw output is text, not JSON.
