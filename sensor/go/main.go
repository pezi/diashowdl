// DiashowDL Sensor Node — Go CLI
//
// Implements the DiashowDL Sensor Interface (see docs/sensor.md).
// Supports BME680 (IAQ) or SCD30 (CO2) via I2C.
//
// - HTTPS REST API on port 9132
// - UDP Discovery on port 9133
//
// Usage:
//
//	cp config.example.json config.json
//	go run main.go
package main

import (
	"crypto/tls"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"runtime"
	"strings"
	"sync"
)

// -- Ports (from sensor spec) ------------------------------------------------

const (
	httpsPort = 9132
	udpPort   = 9133
)

// -- Configuration -----------------------------------------------------------

type config struct {
	APIKey   string `json:"api_key"`
	Sensor   string `json:"sensor"`
	Hostname string `json:"hostname"`
	I2CBus   int    `json:"i2c_bus"`
	SSLCert  string `json:"ssl_cert"`
	SSLKey   string `json:"ssl_key"`
}

func loadConfig() config {
	data, err := os.ReadFile("config.json")
	if err != nil {
		fmt.Fprintln(os.Stderr,
			"Error: config.json not found.\n"+
				"Copy config.example.json to config.json and edit it.")
		os.Exit(1)
	}
	cfg := config{
		Sensor:  "BME680",
		I2CBus:  1,
		SSLCert: "cert.pem",
		SSLKey:  "key.pem",
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing config.json: %v\n", err)
		os.Exit(1)
	}
	cfg.Sensor = strings.ToUpper(cfg.Sensor)
	return cfg
}

// -- Sensor Abstraction ------------------------------------------------------

type sensorReading map[string]any

type sensor interface {
	Name() string
	Read() sensorReading
	ReadDiscovery() sensorReading
	Close()
}

// -- Rounding Helper ---------------------------------------------------------

func round(value float64, places int) float64 {
	factor := math.Pow(10, float64(places))
	return math.Round(value*factor) / factor
}

// -- BME680 IAQ Calculation --------------------------------------------------

const (
	gasBurnIn        = 50
	humidityBaseline = 40.0
	humidityWeight   = 0.25
)

type iaqCalculator struct {
	gasData []uint32
	lastIAQ int
}

func newIAQCalculator() *iaqCalculator {
	data := make([]uint32, gasBurnIn)
	return &iaqCalculator{gasData: data}
}

func (c *iaqCalculator) calculate(gasResistance uint32, humidity float64) int {
	// Shift window and append new reading
	copy(c.gasData, c.gasData[1:])
	c.gasData[gasBurnIn-1] = gasResistance

	var sum uint64
	for _, v := range c.gasData {
		sum += uint64(v)
	}
	gasBaseline := float64(sum) / float64(gasBurnIn)
	if gasBaseline == 0 {
		return c.lastIAQ
	}

	gasOffset := gasBaseline - float64(gasResistance)
	humOffset := humidity - humidityBaseline

	var humScore float64
	if humOffset > 0 {
		humScore = (100.0 - humidityBaseline - humOffset) /
			(100.0 - humidityBaseline) * (humidityWeight * 100.0)
	} else {
		humScore = (humidityBaseline + humOffset) /
			humidityBaseline * (humidityWeight * 100.0)
	}

	gasWeight := 100.0 - (humidityWeight * 100.0)
	var gasScore float64
	if gasOffset > 0 {
		gasScore = float64(gasResistance) / gasBaseline * gasWeight
	} else {
		gasScore = gasWeight
	}

	c.lastIAQ = int(math.Round(humScore + gasScore))
	return c.lastIAQ
}

// -- SCD30 CRC-8 -------------------------------------------------------------

func crc8(data []byte) byte {
	crc := byte(0xFF)
	for _, b := range data {
		crc ^= b
		for i := 0; i < 8; i++ {
			if crc&0x80 != 0 {
				crc = (crc << 1) ^ 0x31
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}

func extractFloat(buf []byte) (float32, bool) {
	if crc8(buf[0:2]) != buf[2] || crc8(buf[3:5]) != buf[5] {
		return 0, false
	}
	bits := binary.BigEndian.Uint32([]byte{buf[0], buf[1], buf[3], buf[4]})
	return math.Float32frombits(bits), true
}

// -- I2C Abstraction ---------------------------------------------------------

// i2cDevice provides a minimal I2C interface.
// On Linux this wraps /dev/i2c-N via periph.io;
// on other platforms it's a stub.
type i2cDevice interface {
	ReadReg(reg byte, buf []byte) error
	Write(data []byte) error
	WriteRead(write []byte, read []byte) error
	Close() error
}

// -- Platform-specific sensor creation (build-tagged in sensor_linux.go
// and sensor_stub.go) --------------------------------------------------------

// createSensor is provided by platform-specific files.
// Declared here so main.go compiles regardless of platform.

// -- Helpers -----------------------------------------------------------------

func getLocalIP() string {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return "127.0.0.1"
	}
	defer conn.Close()
	addr := conn.LocalAddr().(*net.UDPAddr)
	return addr.IP.String()
}

func getHostname() string {
	name, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return name
}

// -- UDP Discovery -----------------------------------------------------------

func startUDPDiscovery(s sensor, hostname string, mu *sync.Mutex) {
	addr, err := net.ResolveUDPAddr("udp4", fmt.Sprintf(":%d", udpPort))
	if err != nil {
		log.Fatalf("Failed to resolve UDP address: %v", err)
	}
	conn, err := net.ListenUDP("udp4", addr)
	if err != nil {
		log.Fatalf("Failed to bind UDP socket: %v", err)
	}
	defer conn.Close()
	fmt.Printf("UDP discovery listening on port %d\n", udpPort)

	buf := make([]byte, 1024)
	for {
		n, remote, err := conn.ReadFromUDP(buf)
		if err != nil {
			continue
		}
		msg := strings.TrimSpace(string(buf[:n]))
		if msg != "DIASHOW_SCAN" {
			continue
		}

		mu.Lock()
		response := sensorReading{
			"type": s.Name(),
			"host": hostname,
			"ip":   getLocalIP(),
			"port": httpsPort,
		}
		for k, v := range s.ReadDiscovery() {
			response[k] = v
		}
		mu.Unlock()

		payload, _ := json.Marshal(response)
		conn.WriteToUDP(payload, remote)
	}
}

// -- HTTPS REST API ----------------------------------------------------------

func startHTTPSServer(s sensor, hostname, apiKey, certFile, keyFile string, mu *sync.Mutex) {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != apiKey {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		mu.Lock()
		data := s.Read()
		name := s.Name()
		mu.Unlock()

		if data == nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{"error": "Sensor read failed"})
			return
		}

		response := sensorReading{
			"sensor": name,
			"host":   hostname,
		}
		for k, v := range data {
			response[k] = v
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(response)
	})

	addr := fmt.Sprintf(":%d", httpsPort)
	fmt.Printf("HTTPS server on port %d\n", httpsPort)

	server := &http.Server{
		Addr:    addr,
		Handler: mux,
		TLSConfig: &tls.Config{
			MinVersion: tls.VersionTLS12,
		},
	}
	if err := server.ListenAndServeTLS(certFile, keyFile); err != nil {
		log.Fatalf("HTTPS server failed: %v", err)
	}
}

// -- Main --------------------------------------------------------------------

func main() {
	fmt.Println("--- DiashowDL Sensor Node (Go) ---")

	cfg := loadConfig()
	hostname := cfg.Hostname
	if hostname == "" {
		hostname = getHostname()
	}

	s := createSensor(cfg.Sensor, cfg.I2CBus)
	defer s.Close()

	fmt.Printf("Sensor: %s on /dev/i2c-%d\n", s.Name(), cfg.I2CBus)
	fmt.Printf("Hostname: %s\n", hostname)

	if runtime.GOOS != "linux" {
		fmt.Fprintln(os.Stderr,
			"Warning: I2C sensors only available on Linux. Using stub sensor.")
	}

	var mu sync.Mutex
	go startUDPDiscovery(s, hostname, &mu)
	startHTTPSServer(s, hostname, cfg.APIKey, cfg.SSLCert, cfg.SSLKey, &mu)
}
