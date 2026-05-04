#!/usr/bin/env python3
"""
DiashowDL Voice Control Demo — Controls diashow via voice commands using Vosk.
Supports uploading .ddl.json shows and .ddlz archives.

Usage:
    python3 api_voice_demo.py <display-ip> <filename> <api-key> [show-in-archive]
"""

import sys
import queue
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from diashow_tools import api, upload_and_start_show, check_console_q, RawTerminal

def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <display-ip> <filename> <api-key> [show-in-archive]")
        sys.exit(1)

    host = sys.argv[1]
    filename = sys.argv[2]
    key = sys.argv[3]
    target_show = sys.argv[4] if len(sys.argv) > 4 else None

    # 1. Upload and Start
    upload_and_start_show(host, key, filename, target_show)
    print("Playback started. Initializing voice model...")

    # 2. Load Vosk Model
    try:
        model = Model(lang="en-us")
    except Exception as e:
        print(f"Failed to load Vosk model: {e}")
        sys.exit(1)
        
    q = queue.Queue()

    def callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        q.put(bytes(indata))

    try:
        device_info = sd.query_devices(None, "input")
        samplerate = int(device_info["default_samplerate"])
        rec = KaldiRecognizer(model, samplerate)

        with sd.RawInputStream(samplerate=samplerate, blocksize=8000, device=None,
                               dtype="int16", channels=1, callback=callback):
            print("\nVOICE MODE ACTIVE")
            print("-----------------")
            print("Commands: 'next' -> Navigate forward")
            print("Commands: 'previous' or 'back' -> Navigate backward")
            print("Press 'q' in this terminal to quit.")
            print("\nListening...\n")

            with RawTerminal():
                while True:
                    if check_console_q():
                        break
                        
                    try:
                        data = q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                        
                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result())
                        text = res.get("text", "")
                        if text:
                            if "next" in text:
                                print(f"Command recognized: '{text}' -> NEXT")
                                api(host, key, "POST", "/api/show/next")
                            elif "previous" in text or "back" in text:
                                print(f"Command recognized: '{text}' -> PREVIOUS")
                                api(host, key, "POST", "/api/show/previous")

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error reading microphone: {e}")
    finally:
        print("\nStopping show and exiting...")
        api(host, key, "POST", "/api/show/stop")

if __name__ == "__main__":
    main()
