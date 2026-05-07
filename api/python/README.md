# DiashowDL Python Tools

A collection of Python-based reference implementations for controlling the DiashowDL Display Server.

## Demos

- **`api_demo.py`**: Standard remote control using arrow keys.
- **`api_hand_demo.py`**: Webcam-based hand gesture control (Swipe Left/Right) using MediaPipe.
- **`api_voice_demo.py`**: Microphone-based voice command control ("next", "previous", "back") using Vosk.

## Setup & Virtual Environment

It is highly recommended to use a Python virtual environment to manage dependencies.

### 1. Create the environment
Navigate to this directory and run:
```bash
python3 -m venv venv
```

### 2. Activate the environment
- **macOS / Linux**:
  ```bash
  source venv/bin/activate
  ```
- **Windows**:
  ```bash
  venv\Scripts\activate
  ```

### 3. Install Dependencies
Choose the requirements file matching the demo you want to run:

- **For Standard Demo (`api_demo.py`)**:
  ```bash
  pip install -r requirements.txt
  ```

- **For Hand Gesture Demo (`api_hand_demo.py`)**:
  ```bash
  pip install -r requirements_hands.txt
  ```

- **For Voice Control Demo (`api_voice_demo.py`)**:
  ```bash
  pip install -r requirements_voice.txt
  ```

*Note: You can install all of them into the same venv if you wish.*

## Usage

All demos follow the same command-line argument structure:

```bash
python <demo_file.py> <display-ip> <show-file> <api-key>
```

### Example
```bash
python api_demo.py 192.168.1.100 ../../diashows/widget_demo.ddl.json my-secret-key

python api_demo.py 192.168.1.100 ../../diashows/amphibia.ddlz my-secret-key
```

## Shared Logic
Common functionality (API communication, terminal handling, show uploading) is encapsulated in `diashow_tools.py` to keep the demo scripts clean and focused on their specific interaction method.
