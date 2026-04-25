"""
Face Recognition Module for Exam Proctoring System
Supports both OpenCV (lightweight) and ArcFace (accurate) methods
"""
import cv2
import time
import numpy as np
from config import FACE_VERIFY_INTERVAL


class OpenCVFaceRecognizer:
    """Lightweight face recognition using OpenCV Haar Cascades"""
    def __init__(self):
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        
        self.reference_face = None
        self.reference_histogram = None
        self.reference_image = None
        self.last_check_time = 0
        self.identity_status = "NOT REGISTERED"
        self.identity_color = (128, 128, 128)
        self.match_confidence = 0.0
        
        print("✓ OpenCV face detector initialized")
        
    def register_face(self, frame):
        """Register reference face using OpenCV"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(100, 100))
        
        if len(faces) == 0:
            return False, "No face detected"
        
        if len(faces) > 1:
            return False, "Multiple faces detected - ensure only one person"
        
        x, y, w, h = faces[0]
        face_roi = gray[y:y+h, x:x+w]
        face_roi_resized = cv2.resize(face_roi, (200, 200))
        
        self.reference_face = face_roi_resized
        self.reference_histogram = cv2.calcHist([face_roi_resized], [0], None, [256], [0, 256])
        cv2.normalize(self.reference_histogram, self.reference_histogram)
        
        self.reference_image = frame.copy()
        
        self.identity_status = "VERIFIED"
        self.identity_color = (0, 255, 0)
        
        return True, "Face registered successfully"
    
    def verify_face(self, frame):
        """Verify face using histogram comparison"""
        if self.reference_face is None:
            return False, "No reference face"
        
        current_time = time.time()
        if current_time - self.last_check_time < FACE_VERIFY_INTERVAL:
            return None, "Waiting"
        
        self.last_check_time = current_time
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(100, 100))
        
        if len(faces) == 0:
            self.identity_status = "NO FACE"
            self.identity_color = (0, 0, 255)
            return False, "No face detected"
        
        if len(faces) > 1:
            self.identity_status = "MULTIPLE FACES"
            self.identity_color = (0, 0, 255)
            return False, "Multiple faces"
        
        x, y, w, h = faces[0]
        face_roi = gray[y:y+h, x:x+w]
        face_roi_resized = cv2.resize(face_roi, (200, 200))
        
        current_hist = cv2.calcHist([face_roi_resized], [0], None, [256], [0, 256])
        cv2.normalize(current_hist, current_hist)
        
        similarity = cv2.compareHist(self.reference_histogram, current_hist, cv2.HISTCMP_CORREL)
        self.match_confidence = float(similarity)
        
        if similarity > 0.7:
            self.identity_status = "VERIFIED"
            self.identity_color = (0, 255, 0)
            return True, f"Match ({similarity:.2f})"
        else:
            self.identity_status = "DIFFERENT PERSON"
            self.identity_color = (0, 0, 255)
            return False, f"No match ({similarity:.2f})"
    
    def get_status(self):
        return self.identity_status, self.identity_color, self.match_confidence


class ArcFaceRecognizer:
    """High-accuracy face recognition using InsightFace ArcFace"""
    def __init__(self):
        """Initialize ArcFace model"""
        print("Loading ArcFace model...")
        try:
            from insightface.app import FaceAnalysis
            
            self.app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            
            self.reference_embedding = None
            self.reference_image = None
            self.last_check_time = 0
            self.identity_status = "NOT REGISTERED"
            self.identity_color = (128, 128, 128)
            self.match_confidence = 0.0
            
            # ArcFace similarity threshold (cosine distance)
            self.similarity_threshold = 0.4  # Lower = more similar
            
            print("✓ ArcFace model initialized")
            
        except ImportError:
            raise ImportError(
                "InsightFace not installed. Install with:\n"
                "pip install insightface onnxruntime"
            )
        
    def register_face(self, frame):
        """Register reference face using ArcFace"""
        faces = self.app.get(frame)
        
        if len(faces) == 0:
            return False, "No face detected"
        
        if len(faces) > 1:
            return False, "Multiple faces detected - ensure only one person"
        
        # Get the face with highest detection confidence
        face = faces[0]
        
        # Extract embedding (512-dimensional feature vector)
        self.reference_embedding = face.embedding
        
        # Store colored version for thumbnail display
        self.reference_image = frame.copy()
        
        self.identity_status = "VERIFIED"
        self.identity_color = (0, 255, 0)
        
        print(f"✓ Face registered with embedding shape: {self.reference_embedding.shape}")
        return True, "Face registered successfully"
    
    def verify_face(self, frame):
        """Verify face using ArcFace embedding comparison"""
        if self.reference_embedding is None:
            return False, "No reference face"
        
        current_time = time.time()
        if current_time - self.last_check_time < FACE_VERIFY_INTERVAL:
            return None, "Waiting"
        
        self.last_check_time = current_time
        
        faces = self.app.get(frame)
        
        if len(faces) == 0:
            self.identity_status = "NO FACE"
            self.identity_color = (0, 0, 255)
            return False, "No face detected"
        
        if len(faces) > 1:
            self.identity_status = "MULTIPLE FACES"
            self.identity_color = (0, 0, 255)
            return False, "Multiple faces"
        
        # Get the face with highest detection confidence
        face = faces[0]
        current_embedding = face.embedding
        
        # Calculate cosine distance (lower = more similar)
        distance = np.linalg.norm(self.reference_embedding - current_embedding)
        
        # Convert to similarity score (0-1, higher = more similar)
        similarity = 1.0 / (1.0 + distance)
        self.match_confidence = float(similarity)
        
        if distance < self.similarity_threshold:
            self.identity_status = "VERIFIED"
            self.identity_color = (0, 255, 0)
            return True, f"Match (dist: {distance:.3f})"
        else:
            self.identity_status = "DIFFERENT PERSON"
            self.identity_color = (0, 0, 255)
            return False, f"No match (dist: {distance:.3f})"
    
    def get_status(self):
        return self.identity_status, self.identity_color, self.match_confidence
    
    def draw_face_boxes(self, frame):
        """Draw bounding boxes around detected faces"""
        faces = self.app.get(frame)
        
        for face in faces:
            bbox = face.bbox.astype(int)
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), 
                         self.identity_color, 2)
        
        return frame