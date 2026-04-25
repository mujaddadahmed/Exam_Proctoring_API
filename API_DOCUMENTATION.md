# ProctorWatch API — Developer Documentation

> Real-time AI-powered exam proctoring as an embeddable service. Your platform owns the candidate — ProctorWatch owns the monitoring.

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Getting Started](#getting-started)
4. [REST API Reference](#rest-api-reference)
5. [WebSocket Protocol](#websocket-protocol)
6. [Webhook Integration](#webhook-integration)
7. [Integrity Report Schema](#integrity-report-schema)
8. [Verdict & Scoring Logic](#verdict--scoring-logic)
9. [Alert Types](#alert-types)
10. [Integration Examples](#integration-examples)
11. [Production Checklist](#production-checklist)

---

## Overview

ProctorWatch is a FastAPI-based proctoring backend that you embed into your exam platform via a simple `<iframe>`. It handles:

- **Face registration** — enrolls the candidate's face at session start
- **Gaze calibration** — establishes a personal baseline for each candidate
- **Live attention monitoring** — tracks head pose, gaze direction, and eye state in real time
- **Identity verification** — periodically re-checks that the same person is still present
- **Sound detection** — flags ambient audio above a configurable threshold
- **Alert delivery** — pushes alerts to your platform via webhook or `postMessage`
- **Integrity reports** — generates a structured JSON report at session end

---

## How It Works

```
Your Platform Backend
        │
        ▼
POST /api/sessions  ──────────────────────────────────┐
        │                                             │
        │  ← session_id + embed_url                  │
        ▼                                             │
<iframe src="{embed_url}"                             │
        allow="camera; microphone">                   │
        │                                             │
        │  (candidate interacts with widget)          │
        ▼                                             │
WebSocket /ws/{session_id}                            │
  • register  (face enrollment)                       │
  • calibrate (gaze baseline)                         │
  • frame     (live monitoring frames)                │
  • end_session                                        │
        │                                             │
        │  Real-time alerts ──────────────────────────┤
        │  via webhook POST or postMessage             │
        │                                             │
        ▼                                             │
GET /api/sessions/{id}/report  ◄─────────────────────┘
```

---

## Getting Started

### Requirements

```
Python 3.10+
OpenCV
MediaPipe
FastAPI
Uvicorn
httpx
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Running the Server

```bash
python server.py
```

Server starts at `http://localhost:8000`.

Interactive API docs are available at `http://localhost:8000/docs`.

---

## REST API Reference

### Health Check

```
GET /health
```

**Response:**

```json
{
  "status": "ok",
  "active_sessions": 2,
  "total_sessions": 5
}
```

---

### Create a Session

```
POST /api/sessions
```

Call this from your **platform backend** before presenting the exam to the candidate. Never call this from the frontend — it is a server-to-server call.

**Request Body:**

```json
{
  "candidate_id":   "cand_001",
  "candidate_name": "Alice Johnson",
  "exam_id":        "midterm_2025",
  "exam_label":     "Midterm — Computer Science",
  "webhook_url":    "https://your-platform.com/webhooks/proctor",
  "metadata":       { "course": "CS101", "instructor": "Dr. Smith" }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `candidate_id` | string | No | Your internal candidate identifier |
| `candidate_name` | string | No | Display name shown in the widget |
| `exam_id` | string | No | Your exam identifier |
| `exam_label` | string | No | Human-readable exam title |
| `webhook_url` | string | No | URL to receive real-time alert POSTs |
| `metadata` | object | No | Arbitrary key-value pairs stored with the report |

**Response `201`:**

```json
{
  "session_id": "a1b2c3d4",
  "embed_url":  "http://localhost:8000/?session_id=a1b2c3d4",
  "ws_url":     "/ws/a1b2c3d4",
  "created_at": "2026-04-24T10:00:00.000000"
}
```

Use `embed_url` as the `src` of your iframe:

```html
<iframe
  src="http://localhost:8000/?session_id=a1b2c3d4"
  allow="camera; microphone"
  width="100%"
  height="600px"
  frameborder="0">
</iframe>
```

---

### List Sessions

```
GET /api/sessions
GET /api/sessions?status=active
```

Optional `status` filter: `waiting`, `connected`, `calibrating`, `active`, `ended`, `disconnected`.

**Response:**

```json
[
  {
    "session_id":     "a1b2c3d4",
    "candidate_name": "Alice Johnson",
    "exam_id":        "midterm_2025",
    "status":         "active",
    "started_at":     "2026-04-24T10:00:00.000000",
    "alert_count":    3
  }
]
```

---

### Get Session Status

```
GET /api/sessions/{session_id}
```

Returns live session state including the last 5 alerts and current attention metrics.

**Response:**

```json
{
  "session_id":     "a1b2c3d4",
  "candidate_name": "Alice Johnson",
  "candidate_id":   "cand_001",
  "exam_id":        "midterm_2025",
  "status":         "active",
  "started_at":     "2026-04-24T10:00:00.000000",
  "current_state": {
    "attention":        "ATTENTIVE",
    "candidate_status": "ATTENTIVE (Direct gaze)",
    "identity":         "VERIFIED",
    "match_confidence": 0.94,
    "sound":            false,
    "sound_level":      0.0012,
    "head_yaw":         -2.3,
    "head_pitch":       5.1,
    "gaze_x":           0.502,
    "gaze_y":           0.491,
    "gaze_dev":         0.008,
    "ear":              0.312,
    "eyes_too_far":     false
  },
  "metrics": { ... },
  "alert_count":    3,
  "recent_alerts":  [ ... ]
}
```

---

### End a Session

```
POST /api/sessions/{session_id}/end
```

Finalizes the session, flushes the CSV log, and locks the report. Safe to call multiple times.

**Response:**

```json
{
  "session_id": "a1b2c3d4",
  "status":     "ended",
  "verdict": {
    "score":  85,
    "result": "PASS",
    "flags":  []
  }
}
```

---

### Get Integrity Report

```
GET /api/sessions/{session_id}/report
GET /api/sessions/{session_id}/report?fmt=text
```

Returns the full integrity report. Pass `?fmt=text` for a plain-text version suitable for logging or email.

See [Integrity Report Schema](#integrity-report-schema) for the full response structure.

---

### Download CSV Log

```
GET /api/sessions/{session_id}/report/csv
```

Downloads the raw per-frame CSV collected during the session. Useful for offline analysis.

**CSV columns:** `timestamp`, `session_time`, `attention_state`, `identity_status`, `sound_detected`, `sound_level`, `head_yaw`, `head_pitch`, `gaze_x`, `gaze_y`, `ear`, `confidence`

---

## WebSocket Protocol

Connect to:

```
ws://localhost:8000/ws/{session_id}
```

All messages are JSON. The widget (`index.html`) handles this automatically — you only need the WebSocket protocol if you are building a custom frontend.

### Message Flow

```
Client                          Server
  │                               │
  │──── ping ────────────────────►│
  │◄─── pong ─────────────────────│
  │                               │
  │──── register (frame) ────────►│  Face enrollment
  │◄─── registered ───────────────│
  │                               │
  │──── calibrate (frames) ──────►│  Repeated ~30 frames
  │◄─── calibrating ──────────────│
  │                               │
  │──── calibrate_done ──────────►│
  │◄─── calibrated ───────────────│
  │                               │
  │──── frame (loop) ────────────►│  Live monitoring
  │◄─── metrics ──────────────────│
  │◄─── alert (when triggered) ───│
  │                               │
  │──── end_session ─────────────►│
  │◄─── session_ended ────────────│
```

---

### Client → Server Messages

#### `ping`
```json
{ "type": "ping" }
```
Keepalive. Server responds with `pong`.

---

#### `register`
Sends a face image for enrollment. Should be called once at session start.

```json
{
  "type": "register",
  "data": "<base64-encoded JPEG, with or without data URI prefix>"
}
```

Server responds with:
```json
{
  "type":    "registered",
  "success": true,
  "message": "Face registered successfully"
}
```

---

#### `calibrate`
Sends calibration frames so the server can measure the candidate's natural head pose and gaze baseline. Send approximately 30 frames while the candidate looks at the center of the screen.

```json
{
  "type": "calibrate",
  "data": "<base64-encoded JPEG>"
}
```

Server responds with:
```json
{
  "type":    "calibrating",
  "samples": 14
}
```

---

#### `calibrate_done`
Signals that calibration is complete. The server computes median baseline values and activates live monitoring.

```json
{ "type": "calibrate_done" }
```

Server responds with:
```json
{
  "type": "calibrated",
  "baseline": {
    "yaw":    -1.45,
    "pitch":   8.30,
    "gaze_x":  0.501,
    "gaze_y":  0.489
  }
}
```

---

#### `frame`
Sends a live monitoring frame. Call this in a loop (target ~10 fps). Include the audio RMS level from the microphone.

```json
{
  "type":      "frame",
  "data":      "<base64-encoded JPEG>",
  "audio_rms": 0.012
}
```

Server responds with a `metrics` message (see below).

---

#### `end_session`
Ends the session from the client side and receives the full report.

```json
{ "type": "end_session" }
```

---

### Server → Client Messages

#### `session_info`
Sent immediately on WebSocket connection.

```json
{
  "type":           "session_info",
  "session_id":     "a1b2c3d4",
  "candidate_name": "Alice Johnson",
  "exam_id":        "midterm_2025",
  "exam_label":     "Midterm — Computer Science"
}
```

---

#### `metrics`
Sent after every `frame` message.

```json
{
  "type": "metrics",
  "state": {
    "attention":        "ATTENTIVE",
    "candidate_status": "ATTENTIVE (Direct gaze)",
    "identity":         "VERIFIED",
    "match_confidence": 0.94,
    "sound":            false,
    "sound_level":      0.0012,
    "head_yaw":         -2.3,
    "head_pitch":        5.1,
    "gaze_x":           0.502,
    "gaze_y":           0.491,
    "gaze_dev":         0.008,
    "ear":              0.312,
    "eyes_too_far":     false
  },
  "metrics": {
    "accuracy":      0.9967,
    "precision":     0.9075,
    "recall":        0.8936,
    "f1_score":      0.9005,
    "total_frames":  450,
    "attentive_pct": 82.4,
    "sound_count":   3,
    "face_pass":     5,
    "face_fail":     1
  }
}
```

---

#### `alert`
Sent when an integrity event is triggered. Also POSTed to your `webhook_url` if configured.

```json
{
  "type":       "alert",
  "event":      "INATTENTIVE",
  "severity":   "warning",
  "message":    "INATTENTIVE (Head and eyes away)",
  "timestamp":  "2026-04-24T10:05:32.123456",
  "session_id": "a1b2c3d4"
}
```

---

#### `session_ended`
Sent in response to `end_session`. Contains the full integrity report.

```json
{
  "type":   "session_ended",
  "report": { ... }
}
```

---

## Webhook Integration

If you pass a `webhook_url` when creating a session, ProctorWatch will POST to it for every alert and when the session ends.

### Alert Webhook Payload

```json
{
  "event":          "IDENTITY_MISMATCH",
  "severity":       "critical",
  "message":        "Confidence 63%",
  "timestamp":      "2026-04-24T10:07:48.000000",
  "session_id":     "a1b2c3d4",
  "candidate_id":   "cand_001",
  "candidate_name": "Alice Johnson",
  "exam_id":        "midterm_2025"
}
```

### Session Ended Webhook Payload

```json
{
  "event":        "SESSION_ENDED",
  "session_id":   "a1b2c3d4",
  "candidate_id": "cand_001",
  "exam_id":      "midterm_2025",
  "timestamp":    "2026-04-24T10:15:00.000000",
  "verdict": {
    "score":  85,
    "result": "PASS",
    "flags":  []
  }
}
```

Webhooks have a 5-second timeout. Failed deliveries are logged server-side but not retried.

---

## Integrity Report Schema

```json
{
  "session_id":       "a1b2c3d4",
  "candidate_id":     "cand_001",
  "candidate_name":   "Alice Johnson",
  "exam_id":          "midterm_2025",
  "exam_label":       "Midterm — Computer Science",
  "metadata":         { },
  "started_at":       "2026-04-24T10:00:00.000000",
  "ended_at":         "2026-04-24T10:15:00.000000",
  "duration_seconds": 900.0,
  "status":           "ended",

  "metrics": {
    "total_frames":       9000,
    "attentive_frames":   7560,
    "inattentive_frames": 1440,
    "attentive_pct":      84.0,
    "accuracy":           0.9967,
    "precision":          0.9075,
    "recall":             0.8936,
    "f1_score":           0.9005,
    "confusion_matrix": {
      "true_positive":  7400,
      "true_negative":  1380,
      "false_positive":  160,
      "false_negative":   60
    }
  },

  "behavioral_events": {
    "sound_detections":        12,
    "face_verifications_pass": 18,
    "face_verifications_fail":  2,
    "total_alerts":             6,
    "alert_breakdown": {
      "INATTENTIVE":       3,
      "IDENTITY_MISMATCH": 0,
      "SOUND_DETECTED":    2,
      "EYES_OFF_SCREEN":   1
    }
  },

  "alert_log": [
    {
      "event":      "INATTENTIVE",
      "severity":   "warning",
      "message":    "INATTENTIVE (Head and eyes away)",
      "timestamp":  "2026-04-24T10:03:15.000000",
      "session_id": "a1b2c3d4"
    }
  ],

  "integrity_verdict": {
    "score":  85,
    "result": "PASS",
    "flags":  []
  }
}
```

---

## Verdict & Scoring Logic

The integrity verdict is computed automatically at session end.

### Results

| Result | Condition |
|---|---|
| `PASS` | Score ≥ 70 **and** zero identity mismatch events |
| `REVIEW` | Score ≥ 45 (but failed PASS condition) |
| `FAIL` | Score < 45 |

### Scoring

Starts at **100**. Each flag deducts **15 points**. Each identity mismatch event deducts an additional **20 points**.

### Flags (automatic)

| Flag | Trigger |
|---|---|
| Candidate inattentive for X% of session | Attentive rate < 50% |
| N identity mismatch event(s) detected | Any `IDENTITY_MISMATCH` critical alert |
| High face verification failure rate (X%) | Face verification failure rate > 30% |
| Excessive audio activity (N detections) | Sound detections > 200 |
| Low classifier accuracy — consider recalibration | Accuracy < 70% |

---

## Alert Types

| Event | Severity | Cooldown | Trigger |
|---|---|---|---|
| `INATTENTIVE` | `warning` | 10s | Attention state is `INATTENTIVE` |
| `IDENTITY_MISMATCH` | `critical` | 20s | Face recognizer returns `DIFFERENT PERSON` |
| `SOUND_DETECTED` | `info` | 8s | Audio RMS > 0.035 |
| `EYES_OFF_SCREEN` | `warning` | 12s | Gaze deviation exceeds threshold |

Cooldowns prevent alert spam — the same alert type will not fire more than once per cooldown window per session.

---

## Integration Examples

### Node.js / Express — Create a session

```javascript
const response = await fetch('http://localhost:8000/api/sessions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    candidate_id:   req.user.id,
    candidate_name: req.user.name,
    exam_id:        exam.id,
    exam_label:     exam.title,
    webhook_url:    'https://your-platform.com/webhooks/proctor',
    metadata:       { course_id: exam.courseId }
  })
});

const { session_id, embed_url } = await response.json();
// Store session_id, render embed_url in your exam page
```

### Python — Create a session

```python
import httpx

resp = httpx.post("http://localhost:8000/api/sessions", json={
    "candidate_id":   "cand_001",
    "candidate_name": "Alice Johnson",
    "exam_id":        "midterm_2025",
    "webhook_url":    "https://your-platform.com/webhooks/proctor"
})

data = resp.json()
session_id = data["session_id"]
embed_url  = data["embed_url"]
```

### Embedding the widget

```html
<!-- In your exam page template -->
<div class="proctor-container">
  <iframe
    id="proctor-widget"
    src="{{ embed_url }}"
    allow="camera; microphone"
    width="320"
    height="240"
    frameborder="0"
    style="border-radius: 8px;">
  </iframe>
</div>
```

### Receiving postMessage events (no webhook needed)

```javascript
window.addEventListener('message', (event) => {
  const { type, event: alertEvent, severity, message } = event.data;

  if (type === 'alert') {
    console.log(`[ProctorWatch] ${severity.toUpperCase()}: ${alertEvent} — ${message}`);

    if (alertEvent === 'IDENTITY_MISMATCH') {
      // Pause exam, notify instructor
    }
  }

  if (type === 'session_ended') {
    const { report } = event.data;
    console.log('Verdict:', report.integrity_verdict.result);
  }
});
```

### Webhook receiver (Express)

```javascript
app.post('/webhooks/proctor', express.json(), (req, res) => {
  const { event, severity, session_id, candidate_id, exam_id, verdict } = req.body;

  if (event === 'IDENTITY_MISMATCH') {
    notifyInstructor({ candidate_id, exam_id, message: 'Identity mismatch detected' });
  }

  if (event === 'SESSION_ENDED') {
    saveReport({ session_id, verdict });
  }

  res.sendStatus(200);
});
```

### Fetching the final report

```javascript
// Call after session ends
const response = await fetch(`http://localhost:8000/api/sessions/${sessionId}/report`);
const report = await response.json();

const { result, score, flags } = report.integrity_verdict;
// result: "PASS" | "REVIEW" | "FAIL"
// score: 0–100
// flags: string[]
```

---

## Production Checklist

- [ ] **Restrict CORS** — change `allow_origins=["*"]` in `server.py` to your platform domain
- [ ] **Use HTTPS/WSS** — the widget requires a secure context for camera/microphone access in production
- [ ] **Persist sessions** — the current store is in-memory; replace `sessions: dict` with a database for multi-process or multi-server deployments
- [ ] **Secure the API** — add authentication (API key header, JWT, etc.) to all `/api/` endpoints
- [ ] **Set `webhook_url`** — use webhooks rather than polling for real-time alert delivery
- [ ] **Tune thresholds** — review `config.py` values (`GAZE_THRESH`, `EAR_THRESH`, `HEAD_YAW_TOL_DEG`, etc.) for your candidate population
- [ ] **Monitor calibration quality** — check that `calibrate_done` baseline values are reasonable (pitch typically 0°–20°, yaw within ±15°) before trusting session results
- [ ] **Handle disconnections** — sessions in `disconnected` status were interrupted; decide whether to allow reconnection or mark as incomplete

---

*ProctorWatch v1.0.0 — FastAPI + OpenCV + MediaPipe*
