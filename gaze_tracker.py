"""
Gaze and Head Pose Tracking Module for Exam Proctoring System
"""
import cv2
import numpy as np
import mediapipe as mp
from config import (
    MODEL_POINTS, POSE_IDX, LEFT_IRIS_IDX, RIGHT_IRIS_IDX,
    LEFT_EYE_EAR_IDX, RIGHT_EYE_EAR_IDX, LEFT_EYE_CORNERS,
    RIGHT_EYE_CORNERS, LEFT_EYE_TOP_BOTTOM, RIGHT_EYE_TOP_BOTTOM
)


class GazeTracker:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        print("✓ MediaPipe Face Mesh initialized")
    
    def solve_head_pose(self, landmarks, img_w, img_h):
        """Calculate head yaw and pitch angles"""
        image_points = np.array([
            (landmarks[POSE_IDX[i]].x * img_w, landmarks[POSE_IDX[i]].y * img_h)
            for i in range(6)
        ], dtype=np.float64)

        focal_length = img_w
        cam_matrix = np.array([[focal_length, 0, img_w/2],
                               [0, focal_length, img_h/2],
                               [0, 0, 1]], dtype=np.float64)
        dist_coeffs = np.zeros((4,1))

        success, rot_vec, _ = cv2.solvePnP(MODEL_POINTS, image_points, cam_matrix, 
                                           dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)
        if not success:
            return None, None
        
        rmat, _ = cv2.Rodrigues(rot_vec)
        sy = np.sqrt(rmat[0,0]**2 + rmat[1,0]**2)
        
        if sy < 1e-6:
            x = np.arctan2(-rmat[1,2], rmat[1,1])
            y = np.arctan2(-rmat[2,0], sy)
        else:
            x = np.arctan2(rmat[2,1], rmat[2,2])
            y = np.arctan2(-rmat[2,0], sy)
        
        return np.degrees(y), np.degrees(x)
    
    def get_iris_centers(self, landmarks, w, h):
        """Calculate iris center positions"""
        try:
            left_pts = np.array([(landmarks[i].x * w, landmarks[i].y * h) for i in LEFT_IRIS_IDX])
            right_pts = np.array([(landmarks[i].x * w, landmarks[i].y * h) for i in RIGHT_IRIS_IDX])
            return np.mean(left_pts, axis=0), np.mean(right_pts, axis=0)
        except:
            return None, None
    
    def eye_aspect_ratio(self, landmarks, eye_idx, w, h):
        """Calculate eye aspect ratio (EAR) for blink detection"""
        pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in eye_idx]
        p = np.array(pts, dtype=np.float32)
        A = np.linalg.norm(p[1] - p[5])
        B = np.linalg.norm(p[2] - p[4])
        C = np.linalg.norm(p[0] - p[3])
        return float((A + B) / (2.0 * C)) if C > 1e-6 else 0.0
    
    def calculate_gaze_position(self, landmarks, w, h):
        """Calculate normalized gaze position (0-1 range)"""
        left_iris, right_iris = self.get_iris_centers(landmarks, w, h)
        
        if left_iris is None:
            return None, None
        
        # Get eye corner landmarks
        left_eye_left = np.array([landmarks[LEFT_EYE_CORNERS[0]].x * w, landmarks[LEFT_EYE_CORNERS[0]].y * h])
        left_eye_right = np.array([landmarks[LEFT_EYE_CORNERS[1]].x * w, landmarks[LEFT_EYE_CORNERS[1]].y * h])
        right_eye_left = np.array([landmarks[RIGHT_EYE_CORNERS[0]].x * w, landmarks[RIGHT_EYE_CORNERS[0]].y * h])
        right_eye_right = np.array([landmarks[RIGHT_EYE_CORNERS[1]].x * w, landmarks[RIGHT_EYE_CORNERS[1]].y * h])
        
        # Get top/bottom landmarks
        left_top = np.array([landmarks[LEFT_EYE_TOP_BOTTOM[0]].x * w, landmarks[LEFT_EYE_TOP_BOTTOM[0]].y * h])
        left_bottom = np.array([landmarks[LEFT_EYE_TOP_BOTTOM[1]].x * w, landmarks[LEFT_EYE_TOP_BOTTOM[1]].y * h])
        right_top = np.array([landmarks[RIGHT_EYE_TOP_BOTTOM[0]].x * w, landmarks[RIGHT_EYE_TOP_BOTTOM[0]].y * h])
        right_bottom = np.array([landmarks[RIGHT_EYE_TOP_BOTTOM[1]].x * w, landmarks[RIGHT_EYE_TOP_BOTTOM[1]].y * h])
        
        # Calculate normalized gaze
        left_gx = (left_iris[0] - left_eye_left[0]) / (left_eye_right[0] - left_eye_left[0] + 1e-6)
        right_gx = (right_iris[0] - right_eye_left[0]) / (right_eye_right[0] - right_eye_left[0] + 1e-6)
        left_gy = (left_iris[1] - left_top[1]) / (left_bottom[1] - left_top[1] + 1e-6)
        right_gy = (right_iris[1] - right_top[1]) / (right_bottom[1] - right_top[1] + 1e-6)
        
        avg_gx = (left_gx + right_gx) / 2.0
        avg_gy = (left_gy + right_gy) / 2.0
        
        return avg_gx, avg_gy, left_iris, right_iris
    
    def process_frame(self, frame):
        """Process a frame and return all tracking data"""
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        
        if not results.multi_face_landmarks:
            return None
        
        landmarks = results.multi_face_landmarks[0].landmark
        
        # Head pose
        yaw, pitch = self.solve_head_pose(landmarks, w, h)
        
        # Gaze position
        gaze_data = self.calculate_gaze_position(landmarks, w, h)
        if gaze_data[0] is None:
            return None
        
        avg_gx, avg_gy, left_iris, right_iris = gaze_data
        
        # Eye aspect ratios
        left_ear = self.eye_aspect_ratio(landmarks, LEFT_EYE_EAR_IDX, w, h)
        right_ear = self.eye_aspect_ratio(landmarks, RIGHT_EYE_EAR_IDX, w, h)
        avg_ear = (left_ear + right_ear) / 2.0
        
        return {
            'yaw': yaw,
            'pitch': pitch,
            'gaze_x': avg_gx,
            'gaze_y': avg_gy,
            'ear': avg_ear,
            'left_iris': left_iris,
            'right_iris': right_iris,
            'landmarks': landmarks
        }
    
    def close(self):
        """Release resources"""
        self.face_mesh.close()