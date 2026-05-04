#!/usr/bin/env python3
"""
DiashowDL CLI — Unified command-line tool for managing DiashowDL
display servers. Used by the Claude Code /diashow skill and as a
standalone tool.

Usage:
    python3 diashow_cli.py <command> [options]

Commands:
    discover                          Find display servers on the network
    status   <ip> <key>               Server status and playback state
    list     <ip> <key>               List shows in the server library
    upload   <ip> <key> <file>        Upload .ddl.json or .ddlz file
    start    <ip> <key> <name>        Start a show [--show=X for archives]
    stop     <ip> <key>               Stop current playback
    next     <ip> <key>               Advance to next slide
    previous <ip> <key>               Go to previous slide
    goto     <ip> <key> <index>       Jump to slide by index
    create   <directory>              Create .ddlz from directory [--output=X]
"""

import argparse
import base64
import json
import os
import socket
import sys
import zipfile

from diashow_tools import api

DISCOVERY_PORT = 9131
DISCOVERY_MAGIC = b"DIASHOW_DISCOVER"
DISCOVERY_TIMEOUT = 3.0

AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".ogg", ".m4a", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
PDF_EXTENSIONS = {".pdf"}


def cmd_discover(args):
    """Broadcast UDP discovery and collect server responses."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(DISCOVERY_TIMEOUT)

    try:
        sock.sendto(DISCOVERY_MAGIC, ("255.255.255.255", DISCOVERY_PORT))
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    servers = []
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            try:
                info = json.loads(data.decode("utf-8"))
                info["ip"] = addr[0]
                servers.append(info)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        except socket.timeout:
            break

    sock.close()
    print(json.dumps(servers, indent=2))


def cmd_status(args):
    """Get server status."""
    result = api(args.ip, args.key, "GET", "/api/status")
    print(json.dumps(result, indent=2))


def cmd_list(args):
    """List shows in the server library."""
    result = api(args.ip, args.key, "GET", "/api/library/list")
    print(json.dumps(result, indent=2))


def cmd_upload(args):
    """Upload a show file to the server."""
    if not os.path.exists(args.file):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        sys.exit(1)

    with open(args.file, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")

    result = api(
        args.ip,
        args.key,
        "POST",
        "/api/library/upload",
        {"name": os.path.basename(args.file), "data": b64_data},
    )
    print(json.dumps(result, indent=2))


def cmd_start(args):
    """Start a show on the server."""
    payload = {"name": args.name}
    if args.show:
        payload["show"] = args.show
    result = api(args.ip, args.key, "POST", "/api/show/start", payload)
    print(json.dumps(result, indent=2))


def cmd_stop(args):
    """Stop current playback."""
    result = api(args.ip, args.key, "POST", "/api/show/stop")
    print(json.dumps(result, indent=2))


def cmd_next(args):
    """Advance to next slide."""
    result = api(args.ip, args.key, "POST", "/api/show/next")
    print(json.dumps(result, indent=2))


def cmd_previous(args):
    """Go to previous slide."""
    result = api(args.ip, args.key, "POST", "/api/show/previous")
    print(json.dumps(result, indent=2))


def cmd_goto(args):
    """Jump to a specific slide."""
    result = api(
        args.ip, args.key, "POST", "/api/show/goto", {"index": args.index}
    )
    print(json.dumps(result, indent=2))


def _asset_folder(filename):
    """Determine the archive subfolder for a given file."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    return "images"


def cmd_create(args):
    """Create a .ddlz archive from a directory."""
    src_dir = os.path.abspath(args.directory)
    if not os.path.isdir(src_dir):
        print(json.dumps({"error": f"Not a directory: {src_dir}"}))
        sys.exit(1)

    # Collect .ddl.json show files
    shows = []
    for name in os.listdir(src_dir):
        if name.endswith(".ddl.json"):
            shows.append(name)

    if not shows:
        print(json.dumps({"error": "No .ddl.json files found in directory"}))
        sys.exit(1)

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        dir_name = os.path.basename(src_dir)
        out_path = os.path.join(os.getcwd(), f"{dir_name}.ddlz")

    # Collect all referenced asset files from the shows
    asset_files = set()
    for show_name in shows:
        show_path = os.path.join(src_dir, show_name)
        try:
            with open(show_path, "r", encoding="utf-8") as f:
                show_data = json.load(f)
            for slide in show_data.get("show", []):
                src = slide.get("src", "")
                if src and not src.startswith(("http://", "https://")):
                    # Strip known URI schemes
                    for prefix in ("asset://", "file://"):
                        if src.startswith(prefix):
                            src = src[len(prefix):]
                            break
                    # Strip leading assets/ if present
                    if src.startswith("assets/"):
                        src = src[len("assets/"):]
                    asset_files.add(src)
                # Check audio sources too
                audio = slide.get("audio", {})
                if isinstance(audio, dict):
                    audio_src = audio.get("src", "")
                    if audio_src and not audio_src.startswith(
                        ("http://", "https://")
                    ):
                        for prefix in ("asset://", "file://"):
                            if audio_src.startswith(prefix):
                                audio_src = audio_src[len(prefix):]
                                break
                        if audio_src.startswith("assets/"):
                            audio_src = audio_src[len("assets/"):]
                        asset_files.add(audio_src)
            # Global audio
            defaults = show_data.get("defaults", {})
            global_audio = defaults.get("audio", {})
            if isinstance(global_audio, dict):
                g_src = global_audio.get("src", "")
                if g_src and not g_src.startswith(("http://", "https://")):
                    for prefix in ("asset://", "file://"):
                        if g_src.startswith(prefix):
                            g_src = g_src[len(prefix):]
                            break
                    if g_src.startswith("assets/"):
                        g_src = g_src[len("assets/"):]
                    asset_files.add(g_src)
        except (json.JSONDecodeError, OSError):
            pass

    # Build the archive
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add show files under diashows/
        for show_name in shows:
            show_path = os.path.join(src_dir, show_name)
            # Rewrite asset URIs to asset:// scheme
            try:
                with open(show_path, "r", encoding="utf-8") as f:
                    show_data = json.load(f)
                _rewrite_sources(show_data)
                rewritten = json.dumps(show_data, indent=2, ensure_ascii=False)
                zf.writestr(f"diashows/{show_name}", rewritten)
            except (json.JSONDecodeError, OSError):
                zf.write(show_path, f"diashows/{show_name}")

        # Add asset files
        added = set()
        for asset in asset_files:
            # Try to find the file relative to src_dir
            candidates = [
                os.path.join(src_dir, asset),
                os.path.join(src_dir, "assets", asset),
            ]
            for candidate in candidates:
                if os.path.isfile(candidate) and candidate not in added:
                    folder = _asset_folder(asset)
                    arc_name = f"{folder}/{os.path.basename(asset)}"
                    zf.write(candidate, arc_name)
                    added.add(candidate)
                    break

    result = {
        "status": "created",
        "archive": out_path,
        "shows": shows,
        "assets": len(added),
    }
    print(json.dumps(result, indent=2))


def _rewrite_sources(show_data):
    """Rewrite local file paths to asset:// URIs for portability."""
    for slide in show_data.get("show", []):
        src = slide.get("src", "")
        if src and not src.startswith(("http://", "https://", "asset://")):
            basename = os.path.basename(src)
            folder = _asset_folder(basename)
            slide["src"] = f"asset://{folder}/{basename}"
        # Per-slide audio
        audio = slide.get("audio", {})
        if isinstance(audio, dict) and "src" in audio:
            a_src = audio["src"]
            if a_src and not a_src.startswith(
                ("http://", "https://", "asset://")
            ):
                basename = os.path.basename(a_src)
                audio["src"] = f"asset://audio/{basename}"
    # Global audio
    defaults = show_data.get("defaults", {})
    global_audio = defaults.get("audio", {})
    if isinstance(global_audio, dict) and "src" in global_audio:
        g_src = global_audio["src"]
        if g_src and not g_src.startswith(
            ("http://", "https://", "asset://")
        ):
            basename = os.path.basename(g_src)
            global_audio["src"] = f"asset://audio/{basename}"


def main():
    parser = argparse.ArgumentParser(
        description="DiashowDL CLI — manage display servers"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    sub.add_parser("discover", help="Find display servers on the network")

    # status
    p = sub.add_parser("status", help="Server status")
    p.add_argument("ip")
    p.add_argument("key")

    # list
    p = sub.add_parser("list", help="List shows in library")
    p.add_argument("ip")
    p.add_argument("key")

    # upload
    p = sub.add_parser("upload", help="Upload a show file")
    p.add_argument("ip")
    p.add_argument("key")
    p.add_argument("file")

    # start
    p = sub.add_parser("start", help="Start a show")
    p.add_argument("ip")
    p.add_argument("key")
    p.add_argument("name")
    p.add_argument("--show", default=None, help="Show name inside archive")

    # stop
    p = sub.add_parser("stop", help="Stop playback")
    p.add_argument("ip")
    p.add_argument("key")

    # next
    p = sub.add_parser("next", help="Next slide")
    p.add_argument("ip")
    p.add_argument("key")

    # previous
    p = sub.add_parser("previous", help="Previous slide")
    p.add_argument("ip")
    p.add_argument("key")

    # goto
    p = sub.add_parser("goto", help="Jump to slide")
    p.add_argument("ip")
    p.add_argument("key")
    p.add_argument("index", type=int)

    # create
    p = sub.add_parser("create", help="Create .ddlz from directory")
    p.add_argument("directory")
    p.add_argument("--output", default=None, help="Output file path")

    args = parser.parse_args()

    commands = {
        "discover": cmd_discover,
        "status": cmd_status,
        "list": cmd_list,
        "upload": cmd_upload,
        "start": cmd_start,
        "stop": cmd_stop,
        "next": cmd_next,
        "previous": cmd_previous,
        "goto": cmd_goto,
        "create": cmd_create,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
