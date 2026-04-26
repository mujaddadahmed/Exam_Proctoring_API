"""
ProctorWatch — FastAPI Proctoring Server
=========================================
Designed for integration with external exam/meeting platforms.
The platform owns the candidate — this service owns the monitoring.

INTEGRATION FLOW:
  1. Platform backend: POST /api/sessions  →  receives session_id + embed_url
  2. Platform embeds:  <iframe src="{embed_url}" allow="camera; microphone">
  3. Candidate opens widget → face registration → calibration → live monitoring
  4. Platform receives real-time alerts via webhook or postMessage
  5. Exam ends: POST /api/sessions/{id}/end  (or widget sends end_session)
  6. Platform fetches: GET /api/sessions/{id}/report

RUNNING:
  python server.py  →  http://localhost:8000
  API docs          →  http://localhost:8000/docs
"""

import asyncio
import base64
import io
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from face_recognizer import OpenCVFaceRecognizer
from gaze_tracker import GazeTracker
from attention_analyzer import AttentionAnalyzer
from metrics import PerformanceMetrics
from config import FACE_VERIFY_INTERVAL

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ProctorWatch API",
    description="""
Real-time exam proctoring service. Designed to be embedded in any LMS,
exam platform, or video-conferencing tool.

**Quick start for platform developers:**
1. `POST /api/sessions` with candidate metadata → get `session_id` + `embed_url`
2. Embed `embed_url` in an `<iframe allow="camera; microphone">`
3. Optionally pass `webhook_url` to receive real-time integrity alerts via POST
4. On exam end: `POST /api/sessions/{id}/end`  (or widget handles it)
5. Fetch `GET /api/sessions/{id}/report` for the full integrity report
    """,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Restrict to your platform domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ── In-memory session store ───────────────────────────────────────────────────
sessions: dict[str, dict] = {}
_alert_cooldowns: dict[str, float] = {}

# ── Pydantic models ───────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    candidate_id:   Optional[str] = None
    candidate_name: Optional[str] = "Candidate"
    exam_id:        Optional[str] = "default"
    exam_label:     Optional[str] = None
    webhook_url:    Optional[str] = None
    metadata:       Optional[dict] = None

# ── Utilities ─────────────────────────────────────────────────────────────────

def decode_frame(b64: str) -> Optional[np.ndarray]:
    try:
        if "," in b64:
            b64 = b64.split(",")[1]
        arr = np.frombuffer(base64.b64decode(b64), np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None

async def fire_webhook(url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(url, json=payload)
    except Exception as e:
        print(f"[Webhook] Failed → {url}: {e}")

def _get_or_404(session_id: str) -> dict:
    if session_id not in sessions:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return sessions[session_id]

# ── Report builder ────────────────────────────────────────────────────────────

def _build_report(s: dict) -> dict:
    m     = s["metrics"].calculate_metrics()
    total = max(s["metrics"].total_frames, 1)
    ended = s.get("ended_at") or datetime.now().isoformat()
    dur   = datetime.fromisoformat(ended).timestamp() - datetime.fromisoformat(s["started_at"]).timestamp()

    return {
        "session_id":     s["id"],
        "candidate_id":   s.get("candidate_id"),
        "candidate_name": s["candidate_name"],
        "exam_id":        s["exam_id"],
        "exam_label":     s.get("exam_label"),
        "metadata":       s.get("metadata", {}),
        "started_at":     s["started_at"],
        "ended_at":       s.get("ended_at"),
        "duration_seconds": round(dur, 1),
        "status":         s["status"],
        "metrics": {
            "total_frames":      s["metrics"].total_frames,
            "attentive_frames":  s["metrics"].attentive_frames,
            "inattentive_frames":s["metrics"].inattentive_frames,
            "attentive_pct":     round(s["metrics"].attentive_frames / total * 100, 2),
            "accuracy":          round(m["accuracy"],  4),
            "precision":         round(m["precision"], 4),
            "recall":            round(m["recall"],    4),
            "f1_score":          round(m["f1_score"],  4),
            "confusion_matrix": {
                "true_positive":  m["true_positive"],
                "true_negative":  m["true_negative"],
                "false_positive": m["false_positive"],
                "false_negative": m["false_negative"],
            },
        },
        "behavioral_events": {
            "sound_detections":        s["metrics"].sound_detected_count,
            "face_verifications_pass": s["metrics"].face_verified_count,
            "face_verifications_fail": s["metrics"].face_failed_count,
            "total_alerts":            len(s["alert_log"]),
            "alert_breakdown": {
                "INATTENTIVE":       sum(1 for a in s["alert_log"] if a["event"] == "INATTENTIVE"),
                "IDENTITY_MISMATCH": sum(1 for a in s["alert_log"] if a["event"] == "IDENTITY_MISMATCH"),
                "SOUND_DETECTED":    sum(1 for a in s["alert_log"] if a["event"] == "SOUND_DETECTED"),
                "EYES_OFF_SCREEN":   sum(1 for a in s["alert_log"] if a["event"] == "EYES_OFF_SCREEN"),
            },
        },
        "alert_log":         s["alert_log"],
        "integrity_verdict": _verdict(m, s),
    }

def _verdict(m: dict, s: dict) -> dict:
    total_checks       = max(s["metrics"].face_verified_count + s["metrics"].face_failed_count, 1)
    identity_fail_rate = s["metrics"].face_failed_count / total_checks
    critical_alerts    = sum(1 for a in s["alert_log"] if a.get("severity") == "critical")
    attn_rate          = s["metrics"].attentive_frames / max(s["metrics"].total_frames, 1)

    flags = []
    if attn_rate < 0.50:
        flags.append(f"Candidate inattentive for {(1-attn_rate)*100:.0f}% of session")
    if critical_alerts > 0:
        flags.append(f"{critical_alerts} identity mismatch event(s) detected")
    if identity_fail_rate > 0.30:
        flags.append(f"High face verification failure rate ({identity_fail_rate*100:.0f}%)")
    if s["metrics"].sound_detected_count > 200:
        flags.append(f"Excessive audio activity ({s['metrics'].sound_detected_count} detections)")
    if m["accuracy"] < 0.70:
        flags.append("Low classifier accuracy — consider recalibration")

    score  = max(0, 100 - len(flags) * 15 - critical_alerts * 20)
    result = "PASS" if score >= 70 and critical_alerts == 0 else "REVIEW" if score >= 45 else "FAIL"
    return {"score": score, "result": result, "flags": flags}

def _text_report(r: dict) -> str:
    v, m, b = r["integrity_verdict"], r["metrics"], r["behavioral_events"]
    lines = [
        "=" * 68,
        "  PROCTORWATCH INTEGRITY REPORT",
        "=" * 68,
        f"  Session     : {r['session_id']}",
        f"  Candidate   : {r['candidate_name']}  ({r.get('candidate_id') or 'N/A'})",
        f"  Exam        : {r.get('exam_label') or r['exam_id']}",
        f"  Started     : {r['started_at'][:19].replace('T',' ')}",
        f"  Ended       : {(r.get('ended_at') or 'in progress')[:19].replace('T',' ')}",
        f"  Duration    : {r.get('duration_seconds',0):.0f}s",
        "-" * 68,
        f"  VERDICT     : {v['result']}   (score {v['score']}/100)",
        "-" * 68,
        "  METRICS",
        f"    Accuracy  : {m['accuracy']*100:.2f}%",
        f"    Precision : {m['precision']*100:.2f}%",
        f"    Recall    : {m['recall']*100:.2f}%",
        f"    F1-Score  : {m['f1_score']*100:.2f}%",
        f"    Attentive : {m['attentive_pct']:.1f}%",
        "-" * 68,
        "  EVENTS",
        f"    Sound     : {b['sound_detections']}",
        f"    Face ✓    : {b['face_verifications_pass']}",
        f"    Face ✗    : {b['face_verifications_fail']}",
        f"    Alerts    : {b['total_alerts']}  " +
        f"(inattentive={b['alert_breakdown']['INATTENTIVE']}  " +
        f"identity={b['alert_breakdown']['IDENTITY_MISMATCH']}  " +
        f"sound={b['alert_breakdown']['SOUND_DETECTED']})",
    ]
    if v["flags"]:
        lines += ["-" * 68, "  FLAGS"]
        for f in v["flags"]:
            lines.append(f"    ⚠  {f}")
    lines.append("=" * 68)
    return "\n".join(lines) + "\n"

# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    return Path("static/index.html").read_text(encoding="utf-8")

@app.get("/health", summary="Health check")
async def health():
    active = sum(1 for s in sessions.values() if s["status"] == "active")
    return {"status": "ok", "active_sessions": active, "total_sessions": len(sessions)}

@app.post("/api/sessions", status_code=201,
          summary="Create a proctoring session",
          description="Call from your platform backend before presenting the exam.")
async def create_session(body: SessionCreateRequest):
    sid      = str(uuid.uuid4())[:8]
    now      = datetime.now().isoformat()

    sessions[sid] = {
        "id":             sid,
        "candidate_id":   body.candidate_id,
        "candidate_name": body.candidate_name or "Candidate",
        "exam_id":        body.exam_id or "default",
        "exam_label":     body.exam_label,
        "webhook_url":    body.webhook_url,
        "metadata":       body.metadata or {},
        "started_at":     now,
        "ended_at":       None,
        "status":         "waiting",
        "face_recognizer":    OpenCVFaceRecognizer(),
        "gaze_tracker":       GazeTracker(),
        "attention_analyzer": None,
        "metrics":            PerformanceMetrics(),
        "csv_rows":           [],
        "last_verify_time":   0,
        "alert_log":          [],
        "current_state":      {},
        "calibration_buffer": {"yaw": [], "pitch": [], "gaze_x": [], "gaze_y": []},
    }

    print(f"[Session {sid}] Created — {body.candidate_name} / {body.exam_id}")
    return {
        "session_id":  sid,
        "embed_url":   f"http://localhost:8000/?session_id={sid}",
        "ws_url":      f"/ws/{sid}",
        "created_at":  now,
    }

@app.get("/api/sessions", summary="List sessions")
async def list_sessions(status: Optional[str] = Query(None)):
    return [
        {"session_id": sid, "candidate_name": s["candidate_name"],
         "exam_id": s["exam_id"], "status": s["status"],
         "started_at": s["started_at"], "alert_count": len(s["alert_log"])}
        for sid, s in sessions.items()
        if not status or s["status"] == status
    ]

@app.get("/api/sessions/{session_id}", summary="Get session status")
async def get_session(session_id: str):
    s = _get_or_404(session_id)
    return {
        "session_id":    session_id,
        "candidate_name":s["candidate_name"],
        "candidate_id":  s.get("candidate_id"),
        "exam_id":       s["exam_id"],
        "status":        s["status"],
        "started_at":    s["started_at"],
        "current_state": s["current_state"],
        "metrics":       s["metrics"].calculate_metrics(),
        "alert_count":   len(s["alert_log"]),
        "recent_alerts": s["alert_log"][-5:],
    }

@app.post("/api/sessions/{session_id}/end",
          summary="End a session",
          description="Flushes CSV and locks the report. Safe to call multiple times.")
async def end_session(session_id: str):
    s = _get_or_404(session_id)
    if s["status"] == "ended":
        return {"session_id": session_id, "status": "ended", "note": "Already ended"}

    s["status"]   = "ended"
    s["ended_at"] = datetime.now().isoformat()
    try: s["gaze_tracker"].close()
    except Exception: pass

    report = _build_report(s)
    print(f"[Session {session_id}] Ended — verdict: {report['integrity_verdict']['result']}")

    if s.get("webhook_url"):
        asyncio.create_task(fire_webhook(s["webhook_url"], {
            "event": "SESSION_ENDED", "session_id": session_id,
            "candidate_id": s.get("candidate_id"), "exam_id": s["exam_id"],
            "timestamp": s["ended_at"], "verdict": report["integrity_verdict"],
        }))

    return {"session_id": session_id, "status": "ended", "verdict": report["integrity_verdict"]}

@app.get("/api/sessions/{session_id}/report",
         summary="Get integrity report",
         description="Full structured report. Pass `?fmt=text` for plain-text version.")
async def get_report(session_id: str, fmt: Optional[str] = Query(None)):
    s = _get_or_404(session_id)
    report = _build_report(s)
    if fmt == "text":
        return HTMLResponse(content=_text_report(report), media_type="text/plain")
    return JSONResponse(content=report)

@app.get("/api/sessions/{session_id}/report/csv",
         summary="Download CSV log",
         description="Raw per-frame CSV collected during the session.")
async def download_csv(session_id: str):
    s = _get_or_404(session_id)
    rows = s.get("csv_rows", [])
    if not rows:
        raise HTTPException(404, "CSV not found — session may not have started monitoring")
    cols = ["timestamp","session_time","attention_state","identity_status",
            "sound_detected","sound_level","head_yaw","head_pitch",
            "gaze_x","gaze_y","ear","confidence"]
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(str(r.get(c,"")) for c in cols))
    csv_bytes = "\n".join(lines).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=proctor_{session_id}.csv"},
    )

# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in sessions:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    s = sessions[session_id]
    if s["status"] == "ended":
        await websocket.send_json({"type": "error", "message": "Session already ended"})
        await websocket.close()
        return

    s["status"] = "connected"
    await websocket.send_json({
        "type": "session_info",
        "session_id":    session_id,
        "candidate_name":s["candidate_name"],
        "exam_id":       s["exam_id"],
        "exam_label":    s.get("exam_label"),
    })

    try:
        while True:
            msg  = json.loads(await websocket.receive_text())
            kind = msg.get("type")

            if kind == "ping":
                await websocket.send_json({"type": "pong"})

            elif kind == "register":
                frame = decode_frame(msg.get("data",""))
                if frame is None:
                    await websocket.send_json({"type":"registered","success":False,"message":"Decode failed"})
                    continue
                ok, text = s["face_recognizer"].register_face(frame)
                if ok: s["status"] = "calibrating"
                await websocket.send_json({"type":"registered","success":ok,"message":text})

            elif kind == "calibrate":
                frame = decode_frame(msg.get("data",""))
                if frame is not None:
                    td  = s["gaze_tracker"].process_frame(frame)
                    buf = s["calibration_buffer"]
                    if td is not None:
                        if td.get("yaw") is not None:   buf["yaw"].append(td["yaw"])
                        if td.get("pitch") is not None: buf["pitch"].append(td["pitch"])
                        buf["gaze_x"].append(td["gaze_x"])
                        buf["gaze_y"].append(td["gaze_y"])
                await websocket.send_json({"type":"calibrating","samples":len(s["calibration_buffer"]["gaze_x"])})

            elif kind == "calibrate_done":
                buf = s["calibration_buffer"]
                by  = float(np.median(buf["yaw"]))    if buf["yaw"]    else 0.0
                bp  = float(np.median(buf["pitch"]))  if buf["pitch"]  else 0.0
                bgx = float(np.median(buf["gaze_x"])) if buf["gaze_x"] else 0.5
                bgy = float(np.median(buf["gaze_y"])) if buf["gaze_y"] else 0.5
                s["attention_analyzer"] = AttentionAnalyzer(by, bp, bgx, bgy)
                s["status"] = "active"
                await websocket.send_json({"type":"calibrated","baseline":
                    {"yaw":round(by,2),"pitch":round(bp,2),"gaze_x":round(bgx,3),"gaze_y":round(bgy,3)}})

            elif kind == "frame" and s["status"] == "active":
                await _process_frame(websocket, s, msg, session_id)

            elif kind == "end_session":
                if s["status"] != "ended":
                    s["status"]   = "ended"
                    s["ended_at"] = datetime.now().isoformat()
                    try: s["gaze_tracker"].close()
                    except Exception: pass
                report = _build_report(s)
                await websocket.send_json({"type": "session_ended", "report": report})
                if s.get("webhook_url"):
                    asyncio.create_task(fire_webhook(s["webhook_url"], {
                        "event":"SESSION_ENDED","session_id":session_id,
                        "candidate_id":s.get("candidate_id"),"exam_id":s["exam_id"],
                        "timestamp":s["ended_at"],"verdict":report["integrity_verdict"],
                    }))
                break

    except WebSocketDisconnect:
        if s["status"] not in ("ended",):
            s["status"] = "disconnected"
        print(f"[Session {session_id}] Disconnected")
    except Exception as e:
        import traceback; traceback.print_exc()

# ── Frame processor ───────────────────────────────────────────────────────────

async def _process_frame(ws: WebSocket, s: dict, msg: dict, session_id: str):
    frame = decode_frame(msg.get("data",""))
    if frame is None: return

    audio_rms      = float(msg.get("audio_rms", 0.0))
    sound_detected = audio_rms > 0.035

    td = s["gaze_tracker"].process_frame(frame)
    ar = s["attention_analyzer"].analyze_frame(td)

    now = time.time()
    fr  = s["face_recognizer"]
    if now - s["last_verify_time"] > FACE_VERIFY_INTERVAL:
        result, _ = fr.verify_face(frame)
        if result is not None:
            s["metrics"].update_identity(result)
            s["last_verify_time"] = now

    identity, _, match_conf = fr.get_status()
    s["metrics"].update(ar["status"] == "ATTENTIVE", ar["candidate_status"].startswith("ATTENTIVE"))
    s["metrics"].update_sound(sound_detected)

    det = ar.get("details") or {}
    state = {
        "attention":        ar["status"],
        "candidate_status": ar["candidate_status"],
        "identity":         identity,
        "match_confidence": round(match_conf, 2),
        "sound":            sound_detected,
        "sound_level":      round(audio_rms, 4),
        "head_yaw":         round(det.get("head_yaw",  0.0), 2),
        "head_pitch":       round(det.get("head_pitch", 0.0), 2),
        "gaze_x":           round((td or {}).get("gaze_x", 0.5), 3),
        "gaze_y":           round((td or {}).get("gaze_y", 0.5), 3),
        "gaze_dev":         round(det.get("gaze_dev", 0.0), 3),
        "ear":              round((td or {}).get("ear", 0.0), 3),
        "eyes_too_far":     det.get("eyes_too_far", False),
    }
    s["current_state"] = state

    session_start = datetime.fromisoformat(s["started_at"]).timestamp()
    s["csv_rows"].append({
        "timestamp": datetime.now().isoformat(),
        "session_time": round(now - session_start, 2),
        "attention_state": state["attention"], "identity_status": state["identity"],
        "sound_detected": state["sound"], "sound_level": state["sound_level"],
        "head_yaw": state["head_yaw"], "head_pitch": state["head_pitch"],
        "gaze_x": state["gaze_x"], "gaze_y": state["gaze_y"],
        "ear": state["ear"], "confidence": state["match_confidence"],
    })

    m     = s["metrics"].calculate_metrics()
    total = max(s["metrics"].total_frames, 1)

    await ws.send_json({
        "type": "metrics",
        "state": state,
        "metrics": {
            "accuracy":      round(m["accuracy"],  4),
            "precision":     round(m["precision"], 4),
            "recall":        round(m["recall"],    4),
            "f1_score":      round(m["f1_score"],  4),
            "total_frames":  s["metrics"].total_frames,
            "attentive_pct": round(s["metrics"].attentive_frames / total * 100, 1),
            "sound_count":   s["metrics"].sound_detected_count,
            "face_pass":     s["metrics"].face_verified_count,
            "face_fail":     s["metrics"].face_failed_count,
        },
    })
    await _check_alerts(ws, s, state, session_id)

# ── Alert engine ─────────────────────────────────────────────────────────────

ALERT_RULES = [
    {"key":"inattentive", "fn": lambda s: s["attention"]=="INATTENTIVE",      "event":"INATTENTIVE",       "severity":"warning",  "cooldown":10, "msg": lambda s: s.get("candidate_status","")},
    {"key":"identity",    "fn": lambda s: s["identity"]=="DIFFERENT PERSON",  "event":"IDENTITY_MISMATCH", "severity":"critical", "cooldown":20, "msg": lambda s: f"Confidence {s['match_confidence']:.0%}"},
    {"key":"sound",       "fn": lambda s: s["sound"],                          "event":"SOUND_DETECTED",    "severity":"info",     "cooldown": 8, "msg": lambda s: f"Level {s['sound_level']:.4f}"},
    {"key":"eyes",        "fn": lambda s: s.get("eyes_too_far"),               "event":"EYES_OFF_SCREEN",   "severity":"warning",  "cooldown":12, "msg": lambda s: f"Gaze dev {s.get('gaze_dev',0):.3f}"},
]

async def _check_alerts(ws: WebSocket, s: dict, state: dict, session_id: str):
    now = time.time()
    for rule in ALERT_RULES:
        if not rule["fn"](state): continue
        ck = f"{session_id}:{rule['key']}"
        if now - _alert_cooldowns.get(ck, 0) < rule["cooldown"]: continue
        _alert_cooldowns[ck] = now

        entry = {
            "event":      rule["event"],
            "severity":   rule["severity"],
            "message":    rule["msg"](state),
            "timestamp":  datetime.now().isoformat(),
            "session_id": session_id,
        }
        s["alert_log"].append(entry)
        await ws.send_json({"type": "alert", **entry})
        if s.get("webhook_url"):
            asyncio.create_task(fire_webhook(s["webhook_url"], {
                **entry,
                "candidate_id":   s.get("candidate_id"),
                "candidate_name": s["candidate_name"],
                "exam_id":        s["exam_id"],
            }))

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
