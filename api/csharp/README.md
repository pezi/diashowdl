# Diashow C# API Demo

A professional .NET 8.0 implementation of the Diashow API client.

## Setup

1.  Navigate to the directory:
    ```bash
    cd tools/api/csharp
    ```
2.  Restore packages:
    ```bash
    dotnet restore
    ```

## Usage

Run the script:

```bash
dotnet run -- <display-ip> <filename> <api-key> [show-in-archive]
```

## Compilation

Build a standalone executable:

```bash
dotnet publish -c Release -r <rid> --self-contained
```
