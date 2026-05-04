# Diashow Node.js API Demo

A professional Node.js implementation of the Diashow API client, allowing you to upload, start, and control presentations via the command line.

## Prerequisites

- Node.js >= 16.0.0
- A running Diashow server

## Setup

1.  Navigate to the directory:
    ```bash
    cd tools/api/nodejs
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```

## Usage

Run the script with the required arguments:

```bash
node index.js <display-ip> <filename> <api-key> [show-in-archive]
```

### Example

```bash
node index.js 192.168.1.100 widget_demo.ddl.json my-secret-key
```

## Controls

-   `Arrow Left`: Previous slide
-   `Arrow Right`: Next slide
-   `q`: Quit and stop the presentation
-   `Ctrl+C`: Force exit
