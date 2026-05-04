package main

import (
	"bufio"
	"bytes"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

const apiPort = 9134

var insecureClient = &http.Client{
	Transport: &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	},
}

func api(host, key, method, path string, body interface{}) (map[string]interface{}, error) {
	url := fmt.Sprintf("https://%s:%d%s", host, apiPort, path)
	var bodyReader io.Reader
	if body != nil {
		jsonBody, _ := json.Marshal(body)
		bodyReader = bytes.NewReader(jsonBody)
	}

	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		return nil, err
	}

	req.Header.Set("X-Api-Key", key)
	req.Header.Set("Content-Type", "application/json")

	resp, err := insecureClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API Error: %d - %s", resp.StatusCode, string(bodyBytes))
	}

	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	return result, nil
}

func main() {
	if len(os.Args) < 4 {
		fmt.Printf("Usage: go run main.go <display-ip> <filename> <api-key> [show-in-archive]\n")
		os.Exit(1)
	}

	host := os.Args[1]
	filename := os.Args[2]
	key := os.Args[3]
	targetShow := ""
	if len(os.Args) > 4 {
		targetShow = os.Args[4]
	}

	fileBytes, err := os.ReadFile(filename)
	if err != nil {
		fmt.Printf("Error: File '%s' not found.\n", filename)
		os.Exit(1)
	}

	// 1. Upload
	fmt.Printf("Uploading to %s:%d...\n", host, apiPort)
	b64Data := base64.StdEncoding.EncodeToString(fileBytes)
	uploadResult, err := api(host, key, "POST", "/api/library/upload", map[string]string{
		"name": filepath.Base(filename),
		"data": b64Data,
	})
	if err != nil {
		fmt.Printf("Upload failed: %v\n", err)
		os.Exit(1)
	}
	showName := uploadResult["name"].(string)
	fmt.Printf("Upload successful: %s\n", showName)

	// 2. Resolve start name
	startName := showName
	if strings.HasSuffix(startName, ".ddl.json") {
		startName = startName[:len(startName)-9]
	} else if strings.HasSuffix(startName, ".json") {
		startName = startName[:len(startName)-5]
	}

	// 3. Stop current show
	fmt.Println("Ensuring server is ready...")
	api(host, key, "POST", "/api/show/stop", nil)

	// 4. Start playback
	fmt.Printf("Starting show '%s'...\n", startName)
	payload := map[string]string{"name": startName}
	if targetShow != "" {
		payload["show"] = targetShow
	}
	result, err := api(host, key, "POST", "/api/show/start", payload)
	if err != nil {
		fmt.Printf("Failed to start show: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Playback started: %v\n", result["name"])

	fmt.Println("\nControls:  <- previous  |  -> next  |  q quit\n")

	// Read keyboard input byte by byte to handle arrow keys
	reader := bufio.NewReader(os.Stdin)
	for {
		b, err := reader.ReadByte()
		if err != nil {
			break
		}
		
		if b == 'q' || b == 'Q' {
			fmt.Println("Stopping show...")
			api(host, key, "POST", "/api/show/stop", nil)
			break
		} else if b == 27 { // ESC - check for arrow keys
			// Read the next two bytes for arrow key sequences
			b2, err := reader.ReadByte()
			if err != nil {
				continue
			}
			if b2 == '[' {
				b3, err := reader.ReadByte()
				if err != nil {
					continue
				}
				if b3 == 'C' { // Right arrow
					api(host, key, "POST", "/api/show/next", nil)
					fmt.Println("-> next")
				} else if b3 == 'D' { // Left arrow
					api(host, key, "POST", "/api/show/previous", nil)
					fmt.Println("<- previous")
				}
			}
		}
	}
}
