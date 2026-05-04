import sys
import os
import base64
import ssl
import requests
import select
import urllib3

from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_PORT = 9134

# Handle Terminal Raw Mode
try:
    import tty
    import termios
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False


class TlsAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", TlsAdapter())


def api(host: str, key: str, method: str, path: str, body: dict | None = None, timeout: int = 5):
    """Generic API call to the Diashow server."""
    url = f"https://{host}:{API_PORT}{path}"
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    if method == "GET":
        r = _session.get(url, headers=headers, timeout=timeout, verify=False)
    else:
        r = _session.post(url, headers=headers, json=body or {}, timeout=timeout, verify=False)
    r.raise_for_status()
    return r.json()


def upload_and_start_show(host: str, key: str, filename: str, target_show: str | None = None):
    """Uploads a show file (.ddl.json or .ddlz archive) and starts playback."""
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)

    # 1. Read and encode file
    with open(filename, "rb") as f:
        file_bytes = f.read()
        b64_data = base64.b64encode(file_bytes).decode("utf-8")

    # 2. Upload to library
    print(f"Uploading '{os.path.basename(filename)}' to {host}:{API_PORT}...")
    try:
        upload_result = api(
            host,
            key,
            "POST",
            "/api/library/upload",
            {"name": os.path.basename(filename), "data": b64_data},
        )
        show_name = upload_result['name']
    except Exception as e:
        print(f"Upload failed: {e}")
        sys.exit(1)

    # 3. Prepare name for start command
    start_name = show_name
    if start_name.endswith(".ddl.json"):
        start_name = start_name[:-9]
    elif start_name.endswith(".json"):
        start_name = start_name[:-5]

    # 4. Stop current show
    try:
        api(host, key, "POST", "/api/show/stop")
    except:
        pass  # Ignore if no show was playing

    # 5. Start playback
    print(f"Starting show '{start_name}'...")
    try:
        payload = {"name": start_name}
        if target_show:
            payload["show"] = target_show
        return api(host, key, "POST", "/api/show/start", payload)
    except Exception as e:
        print(f"Failed to start show: {e}")
        sys.exit(1)


def check_console_q():
    """Returns True if 'q' was pressed in the console (non-blocking)."""
    if not HAS_TERMIOS:
        return False
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1).lower() == 'q'
    return False


class RawTerminal:
    """Context manager for terminal raw/cbreak mode."""

    def __enter__(self):
        if HAS_TERMIOS:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if HAS_TERMIOS:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)


def read_key():
    try:
        import tty, termios, os, select
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = os.read(fd, 1)
            if ch == b"\x1b":
                ready = select.select([fd], [], [], 0.05)[0]
                if ready:
                    rest = os.read(fd, 2)
                    if rest == b"[D" or rest == b"OD": return "left"
                    if rest == b"[C" or rest == b"OC": return "right"
                    if rest == b"[A" or rest == b"OA": return "up"
                    if rest == b"[B" or rest == b"OB": return "down"
                    if rest[0:1] == b"D": return "left"
                    if rest[0:1] == b"C": return "right"
                    if rest[0:1] == b"A": return "up"
                    if rest[0:1] == b"B": return "down"
                return "escape"
            return ch.decode("utf-8", errors="ignore")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except ImportError:
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
<<<<<<< HEAD
            return {b"K": "left", b"M": "right", b"H": "up", b"P": "down"}.get(
                ch2, ""
            )
=======
            return {b"K": "left", b"M": "right",
                    b"H": "up",   b"P": "down"}.get(ch2, "")
>>>>>>> 7f4c5eb (API Scripts for diffrent Lang.(Java Go))
        return ch.decode("utf-8", errors="ignore")