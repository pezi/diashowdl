# Diashow Dart API Demo

A native Dart implementation of the Diashow API client.

## Setup

1.  Navigate to the directory:
    ```bash
    cd tools/api/dart
    ```
2.  Install dependencies:
    ```bash
    dart pub get
    ```

## Usage

Run the script:

```bash
dart bin/api_demo.dart <display-ip> <filename> <api-key> [show-in-archive]
```

## Compilation

You can compile this to a self-contained native executable:

```bash
dart compile exe bin/api_demo.dart -o diashow-cli
./diashow-cli <args>
```
