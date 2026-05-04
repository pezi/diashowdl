# DiashowDL REST API

HTTP REST API for third-party remote control of DiashowDL.

## Setup

1. Open **Settings > General Configuration**
2. Enter an **API Key** (minimum 8 characters, no spaces)
3. Enable **API Interface Active**
4. Start the **Display Server** — the API starts automatically on port **9134**

## Authentication

All requests require the `X-Api-Key` header:

```
X-Api-Key: your-api-key
```

## Base URL

```
https://<display-ip>:9134
```

> The API server uses a device-unique self-signed TLS certificate. Clients
> must disable certificate verification (e.g., `curl -k`,
> `requests.get(..., verify=False)`).

---

## Endpoints

### GET /api/status

Returns the current server status.

**Response:**
```json
{
  "status": "ok",
  "playing": false
}
```

---

### GET /api/library/list

Lists all shows and archives in the library. For archives (`.ddlz`), the
contained show files are also listed.

**Response:**
```json
{
  "shows": [
    {
      "name": "nature.ddl.json",
      "type": "file"
    },
    {
      "name": "demo.ddlz",
      "type": "archive",
      "contents": ["presentation.ddl.json", "gallery.ddl.json"]
    }
  ]
}
```

---

### POST /api/library/upload

Upload a `.ddl.json` or `.ddlz` file to the show library.

**Request body:**
```json
{
  "name": "myshow.ddlz",
  "data": "<base64-encoded archive content>"
}
```

The `name` field is used to determine the file type. It is recommended
to include the correct extension (`.ddl.json` or `.ddlz`).

**Response:**
```json
{
  "status": "uploaded",
  "name": "myshow.ddlz"
}
```

---

### POST /api/show/start

Start a diashow from the library.

**Request body (JSON show):**
```json
{
  "name": "nature"
}
```

**Request body (DDLZ archive):**
```json
{
  "name": "demo.ddlz",
  "show": "presentation"
}
```

The `name` field is auto-extended if no extension is given — the server
checks for `.ddl.json` first, then `.ddlz`.

The `show` field selects which diashow to play from the archive. If
omitted, the first show in the archive is used. The show name is also
auto-extended (e.g., `presentation` → `presentation.ddl.json`).

**Response:**
```json
{
  "status": "started",
  "name": "nature.ddl.json"
}
```

---

### POST /api/show/next

Advance to the next slide.

**Response:**
```json
{"status": "ok"}
```

---

### POST /api/show/previous

Go to the previous slide.

**Response:**
```json
{"status": "ok"}
```

---

### POST /api/show/goto

Jump to a specific slide index.

**Request body:**
```json
{
  "index": 3
}
```

**Response:**
```json
{"status": "ok"}
```

---

### POST /api/show/stop

Stop the current diashow and return to the waiting screen.

**Response:**
```json
{"status": "ok"}
```

---

### POST /api/cache/clear

Clear the on-device image cache (disk + in-memory). Use this after
updating images on the origin server to force fresh downloads on the
next show playback. Equivalent to the **Reset Cache** button in
*Settings > General Configuration*.

**Response:**
```json
{"status": "cleared"}
```

**Error (500):**
```json
{"error": "Failed to clear cache: <reason>"}
```

---

## Error Responses

All errors return a JSON object with an `error` field:

```json
{"error": "Invalid or missing API key"}
```

| Status | Meaning |
|--------|---------|
| 401    | Invalid or missing API key |
| 400    | Bad request (missing fields) |
| 404    | Show or endpoint not found |
| 500    | Internal server error |

---

## Example: curl

```bash
API_KEY="my-secret-key"
HOST="192.168.1.100"

# Check status
curl -k -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/status

# List library
curl -k -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/library/list

# Upload a show
curl -k -X POST -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"myshow.ddl.json\", \"data\": \"$(base64 -i myshow.ddl.json)\"}" \
  https://$HOST:9134/api/library/upload

# Start a show
curl -k -X POST -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "nature"}' \
  https://$HOST:9134/api/show/start

# Next slide
curl -k -X POST -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/show/next

# Previous slide
curl -k -X POST -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/show/previous

# Jump to slide 3
curl -k -X POST -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"index": 3}' \
  https://$HOST:9134/api/show/goto

# Stop show
curl -k -X POST -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/show/stop

# Clear image cache
curl -k -X POST -H "X-Api-Key: $API_KEY" https://$HOST:9134/api/cache/clear
```
