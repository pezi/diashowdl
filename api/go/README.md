# Diashow Go API Demo

A fast, native Go implementation of the Diashow API client.

## Setup

1.  Navigate to the directory:
    ```bash
    cd tools/api/go
    ```
2.  (Optional) Install terminal support for arrow keys:
    ```bash
    go get golang.org/x/term
    ```

## Usage

Run the script:

```bash
go run main.go <display-ip> <filename> <api-key> [show-in-archive]
```

## Compilation

Build a single-binary executable:

```bash
go build -o diashow-cli
./diashow-cli <args>
```
