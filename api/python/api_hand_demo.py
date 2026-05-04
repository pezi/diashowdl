#!/usr/bin/env python3
"""
DiashowDL Hand Gesture Demo — Controls diashow via webcam.
Supports uploading .ddl.json shows and .ddlz archives.

Usage:
    python3 api_hand_demo.py <display-ip> <filename> <api-key> [show-in-archive]
"""

import sys
import os
import time
import cv2
import urllib.request
from diashow_tools import api, upload_and_start_show, check_console_q, RawTerminal

# Resolve model path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
except ImportError as e:
    print(f"\nError: MediaPipe initialization failed: {e}")
    sys.exit(1)

SWIPE_THRESHOLD = 0.08
SWIPE_COOLDOWN = 1.0
BUFFER_SIZE = 5
FEEDBACK_DURATION = 0.8

def download_model():
    if not os.path.exists(MODEL_PATH):
        print(f"Downloading model to {MODEL_PATH}...")
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

def draw_landmarks(frame, landmarks, color=(0, 255, 0)):
    h, w, _ = frame.shape
    for lm in landmarks:
        cx, cy = int(lm.x * w), int(lm.y * h)
        cv2.circle(frame, (cx, cy), 5, color, -1)

def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <display-ip> <filename> <api-key> [show-in-archive]")
        sys.exit(1)

    host = sys.argv[1]
    filename = sys.argv[2]
    key = sys.argv[3]
    target_show = sys.argv[4] if len(sys.argv) > 4 else None
    
    download_model()

    # 1. Upload and Start
    upload_and_start_show(host, key, filename, target_show)

    # 2. Setup Detector
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options, num_hands=2,
        min_hand_detection_confidence=0.5,
        running_mode=vision.RunningMode.IMAGE
    )
    detector = vision.HandLandmarker.create_from_options(options)
    
    cap = cv2.VideoCapture(0)
    last_action_time = 0
    feedback_text = ""
    feedback_until = 0
    history = {"Left": [], "Right": []}

    print("\nGESTURE MODE ACTIVE")
    print("-------------------")
    print("Press 'q' in this terminal OR the camera window to quit.")

    with RawTerminal():
        try:
            while cap.isOpened():
                success, frame = cap.read()
                if not success: break

                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                result = detector.detect(mp_image)

                now = time.time()
                
                if result.hand_landmarks:
                    for idx, landmarks in enumerate(result.hand_landmarks):
                        label = result.handedness[idx][0].category_name
                        draw_landmarks(frame, landmarks)
                        
                        cx = landmarks[0].x
                        history[label].append(cx)
                        if len(history[label]) > BUFFER_SIZE: history[label].pop(0)

                        if len(history[label]) == BUFFER_SIZE and (now - last_action_time) > SWIPE_COOLDOWN:
                            delta = history[label][-1] - history[label][0]
                            if abs(delta) > SWIPE_THRESHOLD:
                                if delta > 0:
                                    api(host, key, "POST", "/api/show/next")
                                    feedback_text = ">> NEXT >>"
                                else:
                                    api(host, key, "POST", "/api/show/previous")
                                    feedback_text = "<< PREVIOUS <<"
                                feedback_until = now + FEEDBACK_DURATION
                                last_action_time = now
                                history[label] = []

                if now < feedback_until:
                    cv2.rectangle(frame, (0, h-60), (w, h), (0, 255, 0), -1)
                    cv2.putText(frame, feedback_text, (w//2 - 120, h - 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
                
                if (now - last_action_time) < SWIPE_COOLDOWN:
                    prog = (now - last_action_time) / SWIPE_COOLDOWN
                    cv2.rectangle(frame, (0, 0), (int(w * prog), 10), (0, 255, 255), -1)

                cv2.imshow('DiashowDL Gesture Control', frame)
                
                # Check for 'q' in Window or Console
                if cv2.waitKey(1) & 0xFF == ord('q') or check_console_q():
                    break
        finally:
            print("\nStopping show and exiting...")
            api(host, key, "POST", "/api/show/stop")
            cap.release()
            cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
