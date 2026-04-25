# ProctorWatch — Exam Proctoring API

> Real-time AI-powered exam proctoring as an embeddable service.  
> Your platform owns the candidate — ProctorWatch owns the monitoring.

**Live API:** `https://examproctoringapi-production.up.railway.app`  
**Interactive Docs:** `https://examproctoringapi-production.up.railway.app/docs`  
**Demo Dashboard:** `https://examproctoringapi-production.up.railway.app/static/platform-dashboard(example usage app).html`

---

## What It Does

ProctorWatch monitors exam candidates in real time via their webcam and microphone. You embed it into your platform with a single `<iframe>` and receive live integrity alerts via webhook or `postMessage`. At the end of the exam you fetch a full integrity report with a PASS / REVIEW / FAIL verdict.

**Capabilities:**
- Face registration & periodic identity verification
- Gaze tracking and head pose estimation
- Attention classification (attentive / inattentive)
- Eye closure detection
- Sound level monitoring
- Real-time alerts with cooldown logic
- Per-session integrity score and report
- Per-frame CSV export

---

## Quick Start (5 Steps)

### Step 1 — Create a session (from your backend)

```bash
curl -X POST https://examproctoringapi-production.up.railway.app/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id":   "cand_001",
    "candidate_name": "Alice Johnson",
    "exam_id":        "midterm_2025",
    "exam_label":     "Midterm — Computer Science",
    "webhook_url":    "https://your-platform.com/webhooks/proctor"
  }'
```

**Response:**
```json
{
  "session_id": "a1b2c3d4",
  "embed_url":  "https://examproctoringapi-production.up.railway.app/?session_id=a1b2c3d4",
  "ws_url":     "/ws/a1b2c3d4",
  "created_at": "2026-04-25T10:00:00.000000"
}
```

### Step 2 — Embed the widget in your exam page

```html
<iframe
  src="https://examproctoringapi-production.up.railway.app/?session_id=a1b2c3d4"
  allow="camera; microphone"
  width="100%"
  height="600px"
  frameborder="0">
</iframe>
```

The widget handles everything automatically:
1. Asks candidate for camera/microphone permission
2. Registers their face
3. Runs gaze calibration
4. Starts live monitoring

### Step 3 — Receive real-time alerts

**Option A — Webhook** (server-to-server, recommended):

```javascript
// Your Express webhook receiver
app.post('/webhooks/proctor', express.json(), (req, res) => {
  const { event, severity, candidate_id, exam_id, message } = req.body;

  if (event === 'IDENTITY_MISMATCH') {
    // Notify instructor, pause exam, flag candidate
  }
  if (event === 'INATTENTIVE') {
    // Log warning, show proctor dashboard alert
  }
  if (event === 'SESSION_ENDED') {
    const { verdict } = req.body;
    // Store result: verdict.result is "PASS", "REVIEW", or "FAIL"
  }

  res.sendStatus(200);
});
```

**Option B — postMessage** (frontend, no server needed):

```javascript
window.addEventListener('message', (event) => {
  const { type, event: alertEvent, severity, message } = event.data;

  if (type === 'alert') {
    console.log(`${severity}: ${alertEvent} — ${message}`);
  }
  if (type === 'session_ended') {
    console.log('Verdict:', event.data.report.integrity_verdict.result);
  }
});
```

### Step 4 — End the session

```bash
curl -X POST https://examproctoringapi-production.up.railway.app/api/sessions/a1b2c3d4/end
```

The widget can also end the session automatically when the candidate submits the exam.

### Step 5 — Fetch the integrity report

```bash
curl https://examproctoringapi-production.up.railway.app/api/sessions/a1b2c3d4/report
```

---

## REST API Reference

Base URL: `https://examproctoringapi-production.up.railway.app`

### `GET /health`
Health check. Verify the server is running.

**Response:**
```json
{ "status": "ok", "active_sessions": 1, "total_sessions": 5 }
```

---

### `POST /api/sessions`
Create a new proctoring session. Call this from your **platform backend** before the exam starts.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `candidate_id` | string | No | Your internal candidate ID |
| `candidate_name` | string | No | Display name shown in widget |
| `exam_id` | string | No | Your exam identifier |
| `exam_label` | string | No | Human-readable exam title |
| `webhook_url` | string | No | URL to receive real-time alert POSTs |
| `metadata` | object | No | Any extra key-value data to store with the report |

**Response `201`:**
```json
{
  "session_id": "a1b2c3d4",
  "embed_url":  "https://examproctoringapi-production.up.railway.app/?session_id=a1b2c3d4",
  "ws_url":     "/ws/a1b2c3d4",
  "created_at": "2026-04-25T10:00:00.000000"
}
```

---

### `GET /api/sessions`
List all sessions. Filter by status with `?status=active`.

**Status values:** `waiting` `connected` `calibrating` `active` `ended` `disconnected`

**Response:**
```json
[
  {
    "session_id":     "a1b2c3d4",
    "candidate_name": "Alice Johnson",
    "exam_id":        "midterm_2025",
    "status":         "active",
    "started_at":     "2026-04-25T10:00:00.000000",
    "alert_count":    3
  }
]
```

---

### `GET /api/sessions/{session_id}`
Get live status of a session including current attention state and recent alerts.

**Response:**
```json
{
  "session_id":     "a1b2c3d4",
  "candidate_name": "Alice Johnson",
  "status":         "active",
  "current_state": {
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
  "alert_count":   3,
  "recent_alerts": [ ... ]
}
```

---

### `POST /api/sessions/{session_id}/end`
End a session and lock the report. Safe to call multiple times.

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

### `GET /api/sessions/{session_id}/report`
Fetch the full integrity report. Add `?fmt=text` for plain-text version.

**Response:**
```json
{
  "session_id":       "a1b2c3d4",
  "candidate_id":     "cand_001",
  "candidate_name":   "Alice Johnson",
  "exam_id":          "midterm_2025",
  "exam_label":       "Midterm — Computer Science",
  "started_at":       "2026-04-25T10:00:00.000000",
  "ended_at":         "2026-04-25T10:15:00.000000",
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
  "alert_log": [ ... ],
  "integrity_verdict": {
    "score":  85,
    "result": "PASS",
    "flags":  []
  }
}
```

---

### `GET /api/sessions/{session_id}/report/csv`
Download the raw per-frame CSV log for offline analysis.

**CSV columns:** `timestamp`, `session_time`, `attention_state`, `identity_status`, `sound_detected`, `sound_level`, `head_yaw`, `head_pitch`, `gaze_x`, `gaze_y`, `ear`, `confidence`

---

## WebSocket Protocol

> The built-in widget (`index.html`) handles the WebSocket automatically. You only need this section if you are building a **custom frontend**.

**Connect to:**
```
wss://examproctoringapi-production.up.railway.app/ws/{session_id}
```

All messages are JSON.

### Message Flow

```
Your Frontend                   ProctorWatch Server
      │                               │
      │──── register (1 frame) ──────►│  Enroll candidate's face
      │◄─── registered ───────────────│
      │                               │
      │──── calibrate (~30 frames) ──►│  Build gaze baseline
      │◄─── calibrating (each) ───────│
      │                               │
      │──── calibrate_done ──────────►│
      │◄─── calibrated ───────────────│
      │                               │
      │──── frame (loop ~10fps) ─────►│  Live monitoring
      │◄─── metrics ──────────────────│
      │◄─── alert (when triggered) ───│
      │                               │
      │──── end_session ─────────────►│
      │◄─── session_ended ────────────│
```

### Messages You Send

#### `register` — enroll face
```json
{ "type": "register", "data": "<base64 JPEG>" }
```
Response: `{ "type": "registered", "success": true, "message": "Face registered successfully" }`

#### `calibrate` — send calibration frames
Send ~30 frames while candidate looks at screen center.
```json
{ "type": "calibrate", "data": "<base64 JPEG>" }
```
Response: `{ "type": "calibrating", "samples": 14 }`

#### `calibrate_done` — finish calibration
```json
{ "type": "calibrate_done" }
```
Response: `{ "type": "calibrated", "baseline": { "yaw": -1.45, "pitch": 8.3, "gaze_x": 0.501, "gaze_y": 0.489 } }`

#### `frame` — live monitoring frame
Send in a loop at ~10 fps. Include microphone audio RMS level.
```json
{ "type": "frame", "data": "<base64 JPEG>", "audio_rms": 0.012 }
```
Response: `metrics` message (see below)

#### `end_session` — close session
```json
{ "type": "end_session" }
```
Response: `session_ended` message with full report

#### `ping` — keepalive
```json
{ "type": "ping" }
```
Response: `{ "type": "pong" }`

### Messages You Receive

#### `metrics` — sent after every frame
```json
{
  "type": "metrics",
  "state": {
    "attention":        "ATTENTIVE",
    "candidate_status": "ATTENTIVE (Direct gaze)",
    "identity":         "VERIFIED",
    "match_confidence": 0.94,
    "sound":            false,
    "head_yaw":         -2.3,
    "head_pitch":        5.1,
    "gaze_dev":         0.008,
    "ear":              0.312,
    "eyes_too_far":     false
  },
  "metrics": {
    "total_frames":  450,
    "attentive_pct": 82.4,
    "accuracy":      0.9967,
    "f1_score":      0.9005,
    "face_pass":     5,
    "face_fail":     1,
    "sound_count":   3
  }
}
```

#### `alert` — integrity event fired
```json
{
  "type":       "alert",
  "event":      "INATTENTIVE",
  "severity":   "warning",
  "message":    "INATTENTIVE (Head and eyes away)",
  "timestamp":  "2026-04-25T10:05:32.123456",
  "session_id": "a1b2c3d4"
}
```

#### `session_ended` — full report on close
```json
{ "type": "session_ended", "report": { ... } }
```

---

## Alert Types

| Event | Severity | Cooldown | Trigger |
|---|---|---|---|
| `INATTENTIVE` | `warning` | 10s | Candidate not looking at screen |
| `IDENTITY_MISMATCH` | `critical` | 20s | Different person detected |
| `SOUND_DETECTED` | `info` | 8s | Audio RMS > 0.035 |
| `EYES_OFF_SCREEN` | `warning` | 12s | Gaze deviation exceeds threshold |

Cooldowns prevent alert spam per session.

---

## Verdict & Scoring

| Result | Condition |
|---|---|
| `PASS` | Score ≥ 70 and zero identity mismatches |
| `REVIEW` | Score ≥ 45 |
| `FAIL` | Score < 45 |

Score starts at **100**. Each flag deducts **15 points**. Each identity mismatch deducts an additional **20 points**.

**Flags triggered by:**
- Attentive rate < 50%
- Any identity mismatch event
- Face verification failure rate > 30%
- Sound detections > 200
- Classifier accuracy < 70%

---

## Webhook Events

Set `webhook_url` when creating a session to receive POST requests for every alert and on session end.

**Alert payload:**
```json
{
  "event":          "IDENTITY_MISMATCH",
  "severity":       "critical",
  "message":        "Confidence 63%",
  "timestamp":      "2026-04-25T10:07:48.000000",
  "session_id":     "a1b2c3d4",
  "candidate_id":   "cand_001",
  "candidate_name": "Alice Johnson",
  "exam_id":        "midterm_2025"
}
```

**Session ended payload:**
```json
{
  "event":      "SESSION_ENDED",
  "session_id": "a1b2c3d4",
  "exam_id":    "midterm_2025",
  "timestamp":  "2026-04-25T10:15:00.000000",
  "verdict":    { "score": 85, "result": "PASS", "flags": [] }
}
```

Webhooks have a 5-second timeout and are not retried on failure.

---

## Code Examples

### Node.js
```javascript
// 1. Create session
const res = await fetch('https://examproctoringapi-production.up.railway.app/api/sessions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    candidate_id:   req.user.id,
    candidate_name: req.user.name,
    exam_id:        exam.id,
    exam_label:     exam.title,
    webhook_url:    'https://your-platform.com/webhooks/proctor'
  })
});
const { session_id, embed_url } = await res.json();

// 2. Embed in your page
// <iframe src={embed_url} allow="camera; microphone" />

// 3. End session
await fetch(`https://examproctoringapi-production.up.railway.app/api/sessions/${session_id}/end`, {
  method: 'POST'
});

// 4. Get report
const report = await fetch(
  `https://examproctoringapi-production.up.railway.app/api/sessions/${session_id}/report`
).then(r => r.json());

console.log(report.integrity_verdict); // { score: 85, result: "PASS", flags: [] }
```

### Python
```python
import httpx

BASE = "https://examproctoringapi-production.up.railway.app"

# 1. Create session
resp = httpx.post(f"{BASE}/api/sessions", json={
    "candidate_id":   "cand_001",
    "candidate_name": "Alice Johnson",
    "exam_id":        "midterm_2025",
    "webhook_url":    "https://your-platform.com/webhooks/proctor"
})
session = resp.json()
session_id = session["session_id"]
embed_url  = session["embed_url"]

# 2. End session
httpx.post(f"{BASE}/api/sessions/{session_id}/end")

# 3. Fetch report
report = httpx.get(f"{BASE}/api/sessions/{session_id}/report").json()
print(report["integrity_verdict"])  # {'score': 85, 'result': 'PASS', 'flags': []}
```

---

## Running Locally

```bash
git clone https://github.com/mujaddadahmed/Exam_Proctoring_API
cd Exam_Proctoring_API
pip install -r requirements.txt
python server.py
```

Server runs at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

> **Note:** Requires Python 3.11. MediaPipe does not support Python 3.12+.

---

## Demo App

A full working example platform is included at:

```
static/platform-dashboard(example usage app).html
```

Access it at:
```
https://examproctoringapi-production.up.railway.app/static/platform-dashboard(example usage app).html
```

Use it to create sessions, watch live monitoring, view alerts, and inspect reports — all without writing any code.

---

## Production Notes

- **CORS** — restrict `allow_origins=["*"]` in `server.py` to your domain before going live
- **Sessions** — currently in-memory; sessions are lost on server restart. Add a database for production
- **Auth** — no authentication is implemented. Add API key or JWT validation to `/api/` endpoints
- **HTTPS/WSS** — required for camera and microphone access in browsers

---

*ProctorWatch v1.0.0 — FastAPI · OpenCV · MediaPipe*
