"""
CSV Data Logging Module for Exam Proctoring System
"""
import csv
import time
from config import CSV_WRITE_INTERVAL


class DataLogger:
    def __init__(self, filename):
        self.filename = filename
        self.data_buffer = []
        self.last_write_time = time.time()
        
        with open(self.filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Session_Time_Seconds', 'Attention_State',
                'Identity_Status', 'Sound_Detected', 'Sound_Level',
                'Head_Yaw', 'Head_Pitch', 'Gaze_X', 'Gaze_Y',
                'Eye_Aspect_Ratio', 'Confidence'
            ])
        print(f"✓ CSV logging initialized: {self.filename}")
    
    def log_data(self, data_dict):
        self.data_buffer.append(data_dict)
        if time.time() - self.last_write_time >= CSV_WRITE_INTERVAL:
            self.write_buffer()
            self.last_write_time = time.time()
    
    def write_buffer(self):
        if not self.data_buffer:
            return
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                for data in self.data_buffer:
                    writer.writerow([
                        data.get('timestamp', ''), data.get('session_time', 0),
                        data.get('attention_state', 'UNKNOWN'), data.get('identity_status', 'UNKNOWN'),
                        data.get('sound_detected', False), data.get('sound_level', 0.0),
                        data.get('head_yaw', 0.0), data.get('head_pitch', 0.0),
                        data.get('gaze_x', 0.0), data.get('gaze_y', 0.0),
                        data.get('ear', 0.0), data.get('confidence', 0.0)
                    ])
            self.data_buffer.clear()
        except Exception as e:
            print(f"Error writing CSV: {e}")
    
    def finalize(self):
        self.write_buffer()
        print(f"✓ CSV completed: {self.filename}")