"""
Sound Detection Module for Exam Proctoring System
"""
import numpy as np
import sounddevice as sd
import threading
import time
from collections import deque
from config import SOUND_THRESHOLD, SOUND_SAMPLE_RATE, SOUND_BLOCK_SIZE, SOUND_SMOOTHING


class SoundDetector:
    def __init__(self, threshold=SOUND_THRESHOLD, sample_rate=SOUND_SAMPLE_RATE):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.sound_levels = deque(maxlen=SOUND_SMOOTHING)
        self.is_sound_detected = False
        self.current_level = 0.0
        self.running = False
        self.stream = None
        self.lock = threading.Lock()
        self.peak_level = 0.0
        self.peak_history = deque(maxlen=10)
        
    def audio_callback(self, indata, frames, time_info, status):
        if status and 'overflow' not in str(status).lower():
            print(f"Sound status: {status}")
        
        try:
            rms = np.sqrt(np.mean(indata**2))
            peak = np.max(np.abs(indata))
            
            with self.lock:
                self.sound_levels.append(float(rms))
                self.peak_history.append(float(peak))
                self.current_level = float(np.mean(self.sound_levels))
                self.peak_level = float(np.max(self.peak_history))
                avg_exceeded = self.current_level > self.threshold
                peak_exceeded = self.peak_level > (self.threshold * 2.5)
                self.is_sound_detected = avg_exceeded or peak_exceeded
        except Exception as e:
            print(f"Audio error: {e}")
    
    def start(self):
        self.running = True
        try:
            device_info = sd.query_devices(kind='input')
            print(f"✓ Audio device: {device_info['name']}")
            
            self.stream = sd.InputStream(
                callback=self.audio_callback,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=SOUND_BLOCK_SIZE,
                dtype='float32',
                latency='low'
            )
            self.stream.start()
            print(f"✓ Sound detection started (threshold: {self.threshold:.4f})")
        except Exception as e:
            print(f"✗ Sound error: {e}")
            try:
                self.stream = sd.InputStream(
                    callback=self.audio_callback,
                    channels=1,
                    samplerate=8000,
                    blocksize=512,
                    dtype='float32'
                )
                self.stream.start()
                self.sample_rate = 8000
                print("✓ Sound detection started (fallback)")
            except:
                self.running = False
    
    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
    
    def get_detailed_status(self):
        with self.lock:
            sensitivity = (self.current_level / self.threshold * 100) if self.threshold > 0 else 0
            return {
                'is_detected': self.is_sound_detected,
                'rms_level': self.current_level,
                'peak_level': self.peak_level,
                'threshold': self.threshold,
                'sensitivity_percent': sensitivity
            }
    
    def adjust_threshold(self, delta):
        with self.lock:
            old = self.threshold
            self.threshold = max(0.001, min(0.5, self.threshold + delta))
            print(f"Threshold: {old:.4f} → {self.threshold:.4f}")
    
    def auto_calibrate(self, duration=3.0):
        print(f"\n🔊 Auto-calibrating sound...")
        print(f"   Stay SILENT for {duration} seconds...")
        
        calibration_samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            with self.lock:
                if len(self.sound_levels) > 0:
                    calibration_samples.append(self.current_level)
            time.sleep(0.1)
            elapsed = time.time() - start_time
            progress = int((elapsed / duration) * 20)
            print(f"\r   [{'=' * progress}{' ' * (20-progress)}] {elapsed:.1f}s", end='')
        
        print()
        
        if calibration_samples:
            ambient_noise = np.mean(calibration_samples)
            noise_std = np.std(calibration_samples)
            suggested_threshold = ambient_noise + (3 * noise_std)
            suggested_threshold = max(0.005, min(0.1, suggested_threshold))
            
            with self.lock:
                self.threshold = suggested_threshold
            
            print(f"   ✓ Calibration complete! Threshold: {self.threshold:.4f}\n")