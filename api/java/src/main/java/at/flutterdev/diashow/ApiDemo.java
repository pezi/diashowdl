package at.flutterdev.diashow;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.file.Files;
import java.security.cert.X509Certificate;
import java.util.Base64;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import com.google.gson.Gson;
import com.google.gson.JsonObject;   

/**
 * DiashowDL Java API Demo — Uploads a show, starts it, and controls it.
 */
public class ApiDemo {

    private static final int API_PORT = 9134;
    private static final Gson gson = new Gson();

    static {
        // Disable hostname verification and certificate checking for self-signed certificates
        javax.net.ssl.HttpsURLConnection.setDefaultHostnameVerifier((hostname, session) -> true);
        
        // Set up insecure SSL context for the application
        try {
            initInsecureSSL();
        } catch (Exception e) {
            System.err.println("Warning: Failed to disable SSL verification: " + e.getMessage());
        }
    }
    
    private static void initInsecureSSL() throws Exception {
        TrustManager[] trustAll = {new X509TrustManager() {
            public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            public void checkClientTrusted(X509Certificate[] certs, String type) {}
            public void checkServerTrusted(X509Certificate[] certs, String type) {}
        }};
        SSLContext sc = SSLContext.getInstance("TLS");
        sc.init(null, trustAll, new java.security.SecureRandom());
        HttpsURLConnection.setDefaultSSLSocketFactory(sc.getSocketFactory());
    }

    public static void main(String[] args) {
        if (args.length < 3) {
            System.err.println("Usage: java -jar api-demo.jar <display-ip> <filename> <api-key> [show-in-archive]");
            System.exit(1);
        }

        String host = args[0];
        String filename = args[1];
        String apiKey = args[2];
        String targetShow = args.length > 3 ? args[3] : null;

        File file = new File(filename);
        if (!file.exists()) {
            System.err.println("Error: File '" + filename + "' not found.");
            System.exit(1);
        }

        try {
            // 1. Read and encode file
            System.out.println("Reading '" + filename + "'...");
            byte[] fileBytes = Files.readAllBytes(file.toPath());
            String b64Data = Base64.getEncoder().encodeToString(fileBytes);

            // 2. Upload to library
            System.out.println("Uploading to " + host + ":" + API_PORT + "...");
            JsonObject uploadBody = new JsonObject();
            uploadBody.addProperty("name", file.getName());
            uploadBody.addProperty("data", b64Data);

            JsonObject uploadResult = post(host, apiKey, "/api/library/upload", uploadBody);
            System.out.println("Upload successful: " + uploadResult.get("name").getAsString());
            String showName = uploadResult.get("name").getAsString();

            // 3. Start the diashow
            String startName = showName;
            if (startName.endsWith(".ddl.json")) {
                startName = startName.substring(0, startName.length() - 9);
            } else if (startName.endsWith(".json")) {
                startName = startName.substring(0, startName.length() - 5);
            }

            System.out.println("Ensuring server is ready...");
            try {
                post(host, apiKey, "/api/show/stop", new JsonObject());
            } catch (Exception e) {
                // Ignore if no show was playing
            }

            String msg = "Starting show '" + startName + "'";
            if (targetShow != null) {
                msg += " (internal show: " + targetShow + ")";
            }
            System.out.println(msg + "...");

            JsonObject startBody = new JsonObject();
            startBody.addProperty("name", startName);
            if (targetShow != null) {
                startBody.addProperty("show", targetShow);
            }

            JsonObject startResult = post(host, apiKey, "/api/show/start", startBody);
            String actualName = startResult.has("name") ? startResult.get("name").getAsString()
                    : startResult.get("archive").getAsString() + " [" + startResult.get("show").getAsString() + "]";
            System.out.println("Playback started: " + actualName);

            System.out.println();
            System.out.println("Controls:  <- (previous) | -> (next) | p (previous) | n (next) | q (quit)");
            System.out.println();

            // Read keyboard input character by character
            while (true) {
                try {
                    int ch = System.in.read();
                    if (ch == -1) break; // EOF
                    
                    if (ch == 'n' || ch == 'N') {
                        post(host, apiKey, "/api/show/next", new JsonObject());
                        System.out.println("-> next");
                    } else if (ch == 'p' || ch == 'P') {
                        post(host, apiKey, "/api/show/previous", new JsonObject());
                        System.out.println("<- previous");
                    } else if (ch == 'q' || ch == 'Q' || ch == 3) { // 3 = Ctrl+C
                        System.out.println("Stopping show...");
                        post(host, apiKey, "/api/show/stop", new JsonObject());
                        System.out.println("Done.");
                        break;
                    } else if (ch == 27) { // ESC - check for arrow keys
                        // Read the next two characters for arrow key sequences
                        int bracket = System.in.read();
                        if (bracket == '[') {
                            int direction = System.in.read();
                            if (direction == 'C') { // Right arrow
                                post(host, apiKey, "/api/show/next", new JsonObject());
                                System.out.println("-> next (right arrow)");
                            } else if (direction == 'D') { // Left arrow
                                post(host, apiKey, "/api/show/previous", new JsonObject());
                                System.out.println("<- previous (left arrow)");
                            }
                        }
                    }
                } catch (Exception e) {
                    System.err.println("Input error: " + e.getMessage());
                    break;
                }
            }

        } catch (Exception e) {
            System.err.println("Operation failed: " + e.getMessage());
            System.exit(1);
        }
    }

    private static JsonObject post(String host, String key, String path, JsonObject body) throws IOException {
        String urlStr = "https://" + host + ":" + API_PORT + path;
        URL url = new URL(urlStr);
        HttpsURLConnection conn = (HttpsURLConnection) url.openConnection();
        
        conn.setRequestMethod("POST");
        conn.setRequestProperty("X-Api-Key", key);
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        
        String jsonBody = gson.toJson(body);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(jsonBody.getBytes("utf-8"));
            os.flush();
        }
        
        int statusCode = conn.getResponseCode();
        String response;
        try (InputStream is = statusCode >= 400 ? conn.getErrorStream() : conn.getInputStream()) {
            response = new String(is.readAllBytes(), "utf-8");
        }
        
        if (statusCode >= 400) {
            throw new IOException("HTTP " + statusCode + ": " + response);
        }
        return gson.fromJson(response, JsonObject.class);
    }
}
