# aep-rate-watch

Polls the Ohio Apples-to-Apples electric chart for AEP residential offers and
pushes an ntfy alert when a fixed-rate, $0-ETF, $0-fee offer appears that beats
the configured current rate by `MIN_IMPROVEMENT` $/kWh.

## Run locally

```bash
pip install -r requirements.txt
CURRENT_RATE=0.0998 NTFY_TOPIC=https://ntfy.sh/my-topic python aep_rate_watch.py
```

State is written to `$RATE_WATCH_STATE` (default `/data/aep_rate_state.json`)
so the same offer isn't alerted on repeatedly.

## Run in Docker

Built and scheduled from `/opt/docker/compose/aep-rate-watch.yml`. With
`POLL_INTERVAL` set, the container loops internally — no external scheduler
needed.

## Env vars

| Var | Default | Notes |
|---|---|---|
| `CURRENT_RATE` | `0.0998` | $/kWh you're locked into |
| `MIN_IMPROVEMENT` | `0.004` | only alert when best beats current by this much |
| `REQUIRE_FIXED` | `true` | fixed-rate offers only |
| `MAX_ETF` | `0` | max early-termination fee ($) |
| `MAX_MONTHLY_FEE` | `0` | max monthly fee ($) |
| `MIN_TERM_MONTHS` / `MAX_TERM_MONTHS` | `12` / `36` | acceptable term window |
| `MONTHLY_KWH` | `1000` | used for "saves ~$X/yr" line |
| `NTFY_TOPIC` | _(unset)_ | full ntfy URL; if unset, alerts print to stderr |
| `POLL_INTERVAL` | `0` | seconds between polls; `0` = run once and exit |
| `AEP_URL` | apples-to-apples URL | override if territory/rate changes |
| `RATE_WATCH_STATE` | `/data/aep_rate_state.json` | state file path |
