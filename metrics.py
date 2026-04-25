"""
Performance Metrics Module for Exam Proctoring System
"""
import time
from config import METRICS_UPDATE_INTERVAL


class PerformanceMetrics:
    def __init__(self):
        # Confusion matrix
        self.true_positive = 0
        self.true_negative = 0
        self.false_positive = 0
        self.false_negative = 0
        
        # Tracking
        self.total_frames = 0
        self.attentive_frames = 0
        self.inattentive_frames = 0
        self.sound_detected_count = 0
        self.face_verified_count = 0
        self.face_failed_count = 0
        
        self.last_metrics_print = time.time()
        
    def update(self, predicted_attentive, actual_attentive):
        """Update confusion matrix"""
        self.total_frames += 1
        
        if predicted_attentive:
            self.attentive_frames += 1
            if actual_attentive:
                self.true_positive += 1
            else:
                self.false_positive += 1
        else:
            self.inattentive_frames += 1
            if actual_attentive:
                self.false_negative += 1
            else:
                self.true_negative += 1
    
    def update_sound(self, detected):
        if detected:
            self.sound_detected_count += 1
    
    def update_identity(self, verified):
        if verified:
            self.face_verified_count += 1
        else:
            self.face_failed_count += 1
    
    def calculate_metrics(self):
        """Calculate precision, recall, F1-score, accuracy"""
        precision = self.true_positive / (self.true_positive + self.false_positive) \
                   if (self.true_positive + self.false_positive) > 0 else 0.0
        
        recall = self.true_positive / (self.true_positive + self.false_negative) \
                if (self.true_positive + self.false_negative) > 0 else 0.0
        
        f1_score = 2 * (precision * recall) / (precision + recall) \
                  if (precision + recall) > 0 else 0.0
        
        accuracy = (self.true_positive + self.true_negative) / self.total_frames \
                  if self.total_frames > 0 else 0.0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'accuracy': accuracy,
            'true_positive': self.true_positive,
            'true_negative': self.true_negative,
            'false_positive': self.false_positive,
            'false_negative': self.false_negative
        }
    
    def print_metrics(self, force=False):
        """Print metrics every interval"""
        current_time = time.time()
        
        if force or (current_time - self.last_metrics_print >= METRICS_UPDATE_INTERVAL):
            metrics = self.calculate_metrics()
            
            print("\n" + "="*70)
            print("📊 PERFORMANCE METRICS")
            print("="*70)
            print(f"Total Frames Processed:     {self.total_frames:,}")
            print(f"Attentive Frames:           {self.attentive_frames:,} ({self.attentive_frames/self.total_frames*100:.1f}%)")
            print(f"Inattentive Frames:         {self.inattentive_frames:,} ({self.inattentive_frames/self.total_frames*100:.1f}%)")
            print("-"*70)
            print("Confusion Matrix:")
            print(f"  True Positives (TP):      {metrics['true_positive']:,}")
            print(f"  True Negatives (TN):      {metrics['true_negative']:,}")
            print(f"  False Positives (FP):     {metrics['false_positive']:,}")
            print(f"  False Negatives (FN):     {metrics['false_negative']:,}")
            print("-"*70)
            print(f"✓ Precision:                {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)")
            print(f"✓ Recall:                   {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)")
            print(f"✓ F1-Score:                 {metrics['f1_score']:.4f} ({metrics['f1_score']*100:.2f}%)")
            print(f"✓ Accuracy:                 {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
            print("-"*70)
            print(f"Sound Detections:           {self.sound_detected_count:,}")
            print(f"Face Verifications (Pass):  {self.face_verified_count:,}")
            print(f"Face Verifications (Fail):  {self.face_failed_count:,}")
            print("="*70 + "\n")
            
            self.last_metrics_print = current_time
            return metrics
        
        return None
    
    def get_summary_report(self):
        """Generate comprehensive end-of-session report"""
        metrics = self.calculate_metrics()
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    FINAL SESSION PERFORMANCE REPORT                  ║
╚══════════════════════════════════════════════════════════════════════╝

📊 OVERALL STATISTICS
{'─'*70}
Total Frames Analyzed:          {self.total_frames:,}
Session Attention Rate:         {self.attentive_frames/self.total_frames*100:.2f}%
Session Inattention Rate:       {self.inattentive_frames/self.total_frames*100:.2f}%

🎯 CLASSIFICATION METRICS
{'─'*70}
Precision:                      {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)
  → Of predicted attentive, {metrics['precision']*100:.1f}% were actually attentive

Recall (Sensitivity):           {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)
  → Of actual attentive states, {metrics['recall']*100:.1f}% were detected

F1-Score:                       {metrics['f1_score']:.4f} ({metrics['f1_score']*100:.2f}%)
  → Harmonic mean of precision and recall

Accuracy:                       {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)
  → Overall correctness of predictions

📈 CONFUSION MATRIX
{'─'*70}
                    Predicted Attentive  |  Predicted Inattentive
Actual Attentive       {metrics['true_positive']:6,}        |       {metrics['false_negative']:6,}
Actual Inattentive     {metrics['false_positive']:6,}        |       {metrics['true_negative']:6,}

🔊 BEHAVIORAL EVENTS
{'─'*70}
Sound Detections:               {self.sound_detected_count:,} times
Face Verifications (Pass):      {self.face_verified_count:,} times
Face Verifications (Fail):      {self.face_failed_count:,} times

💡 PERFORMANCE INTERPRETATION
{'─'*70}
"""
        if metrics['accuracy'] >= 0.9:
            report += "Excellent: System performed with high accuracy (≥90%)\n"
        elif metrics['accuracy'] >= 0.8:
            report += "Good: System performed well (80-90%)\n"
        elif metrics['accuracy'] >= 0.7:
            report += "Fair: System performed adequately (70-80%)\n"
        else:
            report += "Poor: System accuracy below 70% - consider recalibration\n"
        
        if metrics['f1_score'] >= 0.85:
            report += "Balanced: Good balance between precision and recall\n"
        else:
            report += "Unbalanced: Consider adjusting detection thresholds\n"
        
        report += "╚" + "═"*70 + "╝\n"
        
        return report