"""
Attention Analysis Module for Exam Proctoring System
"""
from collections import deque
import numpy as np
from config import (
    HEAD_YAW_TOL_DEG, HEAD_PITCH_TOL_DEG, GAZE_THRESH, GAZE_RELAXED,
    COMPENSATION_MIN, COMPENSATION_PITCH_MIN, EAR_THRESH, EYE_CLOSED_CONSEC,
    SMOOTH_WINDOW, HOLD_FRAMES, MAX_GAZE_DEVIATION
)


class AttentionAnalyzer:
    def __init__(self, baseline_yaw=0.0, baseline_pitch=0.0, baseline_gaze_x=0.5, baseline_gaze_y=0.5):
        self.baseline_yaw = baseline_yaw
        self.baseline_pitch = baseline_pitch
        self.baseline_gaze_x = baseline_gaze_x
        self.baseline_gaze_y = baseline_gaze_y
        
        # Smoothing buffers
        self.gaze_x_buf = deque(maxlen=SMOOTH_WINDOW)
        self.gaze_y_buf = deque(maxlen=SMOOTH_WINDOW)
        self.yaw_buf = deque(maxlen=SMOOTH_WINDOW)
        self.pitch_buf = deque(maxlen=SMOOTH_WINDOW)
        
        # State tracking
        self.eye_closed_counter = 0
        self.attentive_hold = 0
        self.inattentive_hold = 0
        self.current_status = "UNKNOWN"
        self.current_color = (0, 0, 255)
        
        print("✓ Attention analyzer initialized")
    
    def update_baseline(self, yaw, pitch, gaze_x, gaze_y):
        """Update baseline calibration values"""
        self.baseline_yaw = yaw
        self.baseline_pitch = pitch
        self.baseline_gaze_x = gaze_x
        self.baseline_gaze_y = gaze_y
        print(f"✓ Baseline updated: Yaw={yaw:.2f}°, Pitch={pitch:.2f}°, Gaze=({gaze_x:.3f}, {gaze_y:.3f})")
    
    def analyze_frame(self, tracking_data):
        """Analyze tracking data and determine attention status"""
        if tracking_data is None:
            # No face detected
            self.inattentive_hold += 1
            self.attentive_hold = 0
            
            if self.inattentive_hold >= HOLD_FRAMES:
                self.current_status = "INATTENTIVE"
                self.current_color = (0, 0, 255)
            
            return {
                'status': self.current_status,
                'color': self.current_color,
                'candidate_status': "NO FACE",
                'candidate_color': (128, 128, 128),
                'details': None
            }
        
        # Extract and smooth data
        yaw = tracking_data['yaw']
        pitch = tracking_data['pitch']
        gaze_x = tracking_data['gaze_x']
        gaze_y = tracking_data['gaze_y']
        ear = tracking_data['ear']
        
        if yaw:
            self.yaw_buf.append(yaw)
            head_yaw = float(np.mean(self.yaw_buf))
        else:
            head_yaw = 0.0
            
        if pitch:
            self.pitch_buf.append(pitch)
            head_pitch = float(np.mean(self.pitch_buf))
        else:
            head_pitch = 0.0
        
        self.gaze_x_buf.append(gaze_x)
        self.gaze_y_buf.append(gaze_y)
        smooth_gx = float(np.mean(self.gaze_x_buf))
        smooth_gy = float(np.mean(self.gaze_y_buf))
        
        # Calculate deviations from baseline
        yaw_delta = head_yaw - self.baseline_yaw
        pitch_delta = head_pitch - self.baseline_pitch
        iris_x_delta = smooth_gx - self.baseline_gaze_x
        iris_y_delta = smooth_gy - self.baseline_gaze_y
        
        gaze_dev = abs(iris_x_delta)
        gaze_dev_y = abs(iris_y_delta)
        head_yaw_dev = abs(yaw_delta)
        head_pitch_dev = abs(pitch_delta)
        
        # Eye closure detection
        if ear < EAR_THRESH:
            self.eye_closed_counter += 1
        else:
            self.eye_closed_counter = max(self.eye_closed_counter - 1, 0)
        
        eyes_closed = self.eye_closed_counter >= EYE_CLOSED_CONSEC
        
        # Head orientation
        head_turned = (head_yaw_dev > HEAD_YAW_TOL_DEG) or (head_pitch_dev > HEAD_PITCH_TOL_DEG)
        head_turned_yaw = head_yaw_dev > HEAD_YAW_TOL_DEG
        head_turned_pitch = head_pitch_dev > HEAD_PITCH_TOL_DEG
        
        # Compensation detection
        yaw_compensating = (yaw_delta * iris_x_delta) < 0 and abs(iris_x_delta) > COMPENSATION_MIN
        pitch_compensating = (pitch_delta * iris_y_delta) < 0 and abs(iris_y_delta) > COMPENSATION_PITCH_MIN
        any_compensation = yaw_compensating or pitch_compensating
        
        total_gaze_deviation = max(gaze_dev, gaze_dev_y)
        eyes_too_far = total_gaze_deviation > MAX_GAZE_DEVIATION
        
        # Decision logic
        if eyes_closed:
            candidate_status = "INATTENTIVE (Eyes closed)"
            candidate_color = (0, 128, 255)
        elif eyes_too_far:
            if head_turned:
                candidate_status = "INATTENTIVE (Head and eyes away)"
                candidate_color = (0, 0, 255)
            else:
                candidate_status = "INATTENTIVE (Eyes looking away)"
                candidate_color = (0, 0, 255)
        else:
            if (gaze_dev <= GAZE_THRESH and gaze_dev_y <= GAZE_THRESH):
                candidate_status = "ATTENTIVE (Direct gaze)"
                candidate_color = (0, 255, 0)
            elif (gaze_dev <= GAZE_RELAXED and gaze_dev_y <= GAZE_RELAXED):
                if head_turned:
                    if any_compensation:
                        if (yaw_compensating and abs(iris_x_delta) > COMPENSATION_MIN * 1.5) or \
                           (pitch_compensating and abs(iris_y_delta) > COMPENSATION_PITCH_MIN * 1.2):
                            candidate_status = "ATTENTIVE (Compensating)"
                            candidate_color = (0, 255, 0)
                        else:
                            candidate_status = "ATTENTIVE (Eyes on screen)"
                            candidate_color = (0, 220, 0)
                    else:
                        candidate_status = "ATTENTIVE (Eyes on screen)"
                        candidate_color = (0, 220, 0)
                else:
                    candidate_status = "ATTENTIVE (Normal)"
                    candidate_color = (0, 255, 0)
            elif any_compensation and not eyes_too_far:
                if gaze_dev <= GAZE_RELAXED * 1.3 and gaze_dev_y <= GAZE_RELAXED * 1.3:
                    if (yaw_compensating and abs(iris_x_delta) > COMPENSATION_MIN * 2.5) or \
                       (pitch_compensating and abs(iris_y_delta) > COMPENSATION_PITCH_MIN * 2):
                        candidate_status = "ATTENTIVE (Strong compensation)"
                        candidate_color = (0, 200, 0)
                    else:
                        candidate_status = "INATTENTIVE (Insufficient compensation)"
                        candidate_color = (0, 0, 255)
                else:
                    candidate_status = "INATTENTIVE (Eyes deviating)"
                    candidate_color = (0, 0, 255)
            elif head_turned_pitch and not head_turned_yaw:
                if pitch_compensating and gaze_dev_y <= GAZE_RELAXED:
                    candidate_status = "ATTENTIVE (Vertical adjustment)"
                    candidate_color = (0, 220, 0)
                else:
                    candidate_status = "INATTENTIVE (Looking up/down)"
                    candidate_color = (0, 0, 255)
            else:
                if head_turned:
                    candidate_status = "INATTENTIVE (Head and eyes away)"
                    candidate_color = (0, 0, 255)
                else:
                    candidate_status = "INATTENTIVE (Looking away)"
                    candidate_color = (0, 0, 255)
        
        # Apply temporal smoothing
        if candidate_status.startswith("ATTENTIVE"):
            self.attentive_hold += 1
            self.inattentive_hold = 0
        else:
            self.inattentive_hold += 1
            self.attentive_hold = 0
        
        if self.attentive_hold >= HOLD_FRAMES:
            self.current_status = "ATTENTIVE"
            self.current_color = (0, 255, 0)
        elif self.inattentive_hold >= HOLD_FRAMES:
            self.current_status = "INATTENTIVE"
            self.current_color = (0, 0, 255)
        
        return {
            'status': self.current_status,
            'color': self.current_color,
            'candidate_status': candidate_status,
            'candidate_color': candidate_color,
            'details': {
                'head_yaw': head_yaw,
                'head_pitch': head_pitch,
                'gaze_dev': gaze_dev,
                'gaze_dev_y': gaze_dev_y,
                'total_gaze_deviation': total_gaze_deviation,
                'yaw_compensating': yaw_compensating,
                'pitch_compensating': pitch_compensating,
                'eyes_too_far': eyes_too_far,
                'iris_x_delta': iris_x_delta,
                'iris_y_delta': iris_y_delta
            }
        }