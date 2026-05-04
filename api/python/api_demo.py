#!/usr/bin/env python3
"""
DiashowDL API Demo — Uploads a show (.ddl.json or .ddlz) to the display server,
starts it, and controls it with arrow keys (left/right = prev/next, q = quit).

Usage:
    python3 api_demo.py <display-ip> <filename> <api-key> [show-in-archive]
"""

import sys
from diashow_tools import api, upload_and_start_show, read_key


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <display-ip> <filename> <api-key> [show-in-archive]")
        sys.exit(1)

    host = sys.argv[1]
    filename = sys.argv[2]
    key = sys.argv[3]
    target_show = sys.argv[4] if len(sys.argv) > 4 else None

    # 1. Upload and Start
    result = upload_and_start_show(host, key, filename, target_show)
    
    actual_name = result.get('name') or f"{result.get('archive')} [{result.get('show')}]"
    print(f"Playback started: {actual_name}")

    print()
    print("Controls:  <- previous  |  -> next  |  q quit")
    print()

    while True:
        k = read_key()
        if k == "left":
            api(host, key, "POST", "/api/show/previous")
            print("<- previous")
        elif k == "right":
            api(host, key, "POST", "/api/show/next")
            print("-> next")
        elif k in ("q", "Q", "\x03"):  # q or Ctrl+C
            print("Stopping show...")
            api(host, key, "POST", "/api/show/stop")
            print("Done.")
            break


if __name__ == "__main__":
    main()
