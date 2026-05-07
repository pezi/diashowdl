# Diashow Java API Demo

A Java 17 implementation of the Diashow API client, built with Maven.

## Setup

1.  Navigate to the directory:
    ```bash
    cd tools/api/java
    ```
2.  Build the shaded JAR (includes Gson and all dependencies):
    ```bash
    mvn clean package
    ```

## Usage

Run the packaged JAR:

```bash
java -jar target/api-demo-1.0-SNAPSHOT.jar <display-ip> <filename> <api-key> [show-in-archive]
```

### Example

```bash
java -jar target/api-demo-1.0-SNAPSHOT.jar 192.168.1.100 ../../diashows/widget_demo.ddl.json my-secret-key

java -jar target/api-demo-1.0-SNAPSHOT.jar 192.168.1.100 ../../diashows/amphibia.ddlz my-secret-key
```

## Controls

-   `Arrow Left` / `p`: Previous slide
-   `Arrow Right` / `n`: Next slide
-   `c`: Clear cache
-   `q`: Quit and stop the presentation

## Notes

The display server uses a device-unique self-signed certificate, so the
client installs an insecure `TrustManager` and disables hostname
verification at startup. This is appropriate for LAN use against a known
display IP — do not reuse this `SSLContext` setup for general-purpose HTTPS
clients.
