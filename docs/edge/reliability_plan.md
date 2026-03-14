# Edge Reliability Plan (T13I)

## Scope
- Runtime: `edge_device/api/server.py`
- Heartbeat: `edge_device/health/heartbeat.py`
- Event queue and backpressure: `edge_device/api/server.py`
- Soak execution: `scripts/edge_soak_test.sh`

## SLO / Acceptance Thresholds
- `take_snapshot` success rate: `>= 99%`
- `take_snapshot` latency P95: `<= 0.80s`
- `get_recent_clip` success rate: `>= 98%`
- `get_recent_clip` latency P95: `<= 1.50s`
- Event ingest (`captured_at -> backend receive`) latency P95: `<= 2.00s`
- Heartbeat online stability: `100% online` during test window

## Reliability Controls
- Event durable queue:
  - On event upload failure, payload is persisted to `EDGE_PENDING_EVENT_DIR`.
  - Queue files are replayed on heartbeat (`pending_flush_batch` capped).
- Backpressure policy:
  - Queue max size: `EDGE_PENDING_EVENT_MAX`.
  - Overflow drop strategy: drop lower-priority pending events first.
  - Priority rule:
    - P0: `security_alert` or `importance >= 4`
    - P1: `object_detected`
    - P5: other events
- Degradation policy:
  - Heartbeat is always sent, even if pending replay fails.
  - `payload.last_upload_ok` reflects replay + heartbeat upload outcome.

## Network Recovery Drill
1. Disable event upload path (simulated network error).
2. Run `run_once` multiple times and verify pending queue growth.
3. Send heartbeat in offline mode (must still return response).
4. Restore event upload path.
5. Send heartbeat again and verify queued events are flushed.

## Security and Audit Notes
- No telemetry bypasses backend APIs.
- Heartbeat and event payloads keep existing schema compatibility (`edge.event.v1`, `edge.heartbeat.v1`).
- Reliability drill and soak output are captured in `docs/edge/soak_test_report.md`.
