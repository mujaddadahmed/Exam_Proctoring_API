"""
Configuration settings for the Exam Proctoring System
"""
import numpy as np
import os
from datetime import datetime

# ----------------- Calibration Config -----------------
CALIBRATION_SECONDS = 2.0
FACE_VERIFY_INTERVAL = 5.0

# ----------------- Sound Detection Config -----------------
SOUND_THRESHOLD = 0.01
SOUND_SAMPLE_RATE = 16000
SOUND_BLOCK_SIZE = 1024
SOUND_SMOOTHING = 20

# ----------------- Head Pose Model Points -----------------
MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),
    (0.0, -63.6, -12.5),
    (-43.3, 32.7, -26.0),
    (43.3, 32.7, -26.0),
    (-28.9, 28.9, -24.1),
    (28.9, 28.9, -24.1)
], dtype=np.float64)

# ----------------- MediaPipe Landmark Indices -----------------
POSE_IDX = [1, 152, 33, 263, 61, 291]
LEFT_IRIS_IDX = [468, 469, 470, 471]
RIGHT_IRIS_IDX = [473, 474, 475, 476]
LEFT_EYE_EAR_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_EAR_IDX = [362, 385, 387, 263, 373, 380]
LEFT_EYE_CORNERS = (33, 133)
RIGHT_EYE_CORNERS = (362, 263)
LEFT_EYE_TOP_BOTTOM = (159, 145)
RIGHT_EYE_TOP_BOTTOM = (386, 374)

# ----------------- Detection Thresholds -----------------
HEAD_YAW_TOL_DEG = 25.0
HEAD_PITCH_TOL_DEG = 22.0
GAZE_THRESH = 0.07
GAZE_RELAXED = 0.12
COMPENSATION_MIN = 0.003
COMPENSATION_PITCH_MIN = 0.015
EAR_THRESH = 0.20
EYE_CLOSED_CONSEC = 3
SMOOTH_WINDOW = 7
HOLD_FRAMES = 6
MAX_GAZE_DEVIATION = 0.20

# ----------------- CSV Logging Config -----------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILENAME = os.path.join(SCRIPT_DIR, f"attention_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
CSV_WRITE_INTERVAL = 1.0

# ----------------- Performance Metrics Config -----------------
METRICS_UPDATE_INTERVAL = 30.0