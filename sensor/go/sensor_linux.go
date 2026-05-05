//go:build linux

package main

import (
	"fmt"
	"os"
	"sync"
	"time"

	"periph.io/x/conn/v3/i2c"
	"periph.io/x/conn/v3/i2c/i2creg"
	"periph.io/x/host/v3"
)

func init() {
	if _, err := host.Init(); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to init periph: %v\n", err)
	}
}

// -- BME680 Sensor -----------------------------------------------------------

// BME680 register addresses and constants.
const (
	bme680Addr        = 0x76
	bme680ChipIDReg   = 0xD0
	bme680ChipID      = 0x61
	bme680CtrlMeasReg = 0x74
	bme680CtrlHumReg  = 0x72
	bme680ConfigReg   = 0x75
	bme680CtrlGas1Reg = 0x71
	bme680GasWait0Reg = 0x64
	bme680ResHeat0Reg = 0x5A
	bme680DataReg     = 0x1D
)

type bme680Sensor struct {
	dev    *i2c.Dev
	bus    i2c.BusCloser
	iaq    *iaqCalculator
	calT   [3]float64
	calP   [10]float64
	calH   [7]float64
	calGH  [3]float64
	resHR  byte
	mu     sync.Mutex
}

func newBME680(i2cBus int) *bme680Sensor {
	bus, err := i2creg.Open(fmt.Sprintf("/dev/i2c-%d", i2cBus))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to open I2C bus: %v\n", err)
		os.Exit(1)
	}
	dev := &i2c.Dev{Bus: bus, Addr: bme680Addr}

	s := &bme680Sensor{
		dev: dev,
		bus: bus,
		iaq: newIAQCalculator(),
	}
	s.readCalibration()
	s.configure()
	return s
}

func (s *bme680Sensor) readReg(reg byte, n int) []byte {
	buf := make([]byte, n)
	if err := s.dev.Tx([]byte{reg}, buf); err != nil {
		return nil
	}
	return buf
}

func (s *bme680Sensor) writeReg(reg, val byte) {
	s.dev.Tx([]byte{reg, val}, nil)
}

func (s *bme680Sensor) readCalibration() {
	// Temperature calibration (par_t1..t3)
	c1 := s.readReg(0xE9, 2)
	c2 := s.readReg(0x8A, 2)
	c3 := s.readReg(0x8C, 1)
	if c1 != nil && c2 != nil && c3 != nil {
		s.calT[0] = float64(uint16(c1[1])<<8 | uint16(c1[0]))
		s.calT[1] = float64(int16(uint16(c2[1])<<8 | uint16(c2[0])))
		s.calT[2] = float64(int8(c3[0]))
	}

	// Pressure calibration (par_p1..p10)
	p := s.readReg(0x8E, 20)
	if p != nil {
		s.calP[0] = float64(uint16(p[1])<<8 | uint16(p[0]))
		s.calP[1] = float64(int16(uint16(p[3])<<8 | uint16(p[2])))
		s.calP[2] = float64(int8(p[4]))
		s.calP[3] = float64(int16(uint16(p[6])<<8 | uint16(p[5])))
		s.calP[4] = float64(int16(uint16(p[8])<<8 | uint16(p[7])))
		s.calP[5] = float64(int8(p[9]))
		s.calP[6] = float64(int8(p[11]))
		s.calP[7] = float64(int16(uint16(p[13])<<8 | uint16(p[12])))
		s.calP[8] = float64(int16(uint16(p[15])<<8 | uint16(p[14])))
		s.calP[9] = float64(uint8(p[16]))
	}

	// Humidity calibration (par_h1..h7)
	h := s.readReg(0xE1, 8)
	h2 := s.readReg(0xE2, 2)
	if h != nil && h2 != nil {
		s.calH[0] = float64(uint16(h[2])<<4 | uint16(h[1]&0x0F))
		s.calH[1] = float64(uint16(h2[0])<<4 | uint16(h[1]>>4))
		s.calH[2] = float64(int8(h[3]))
		s.calH[3] = float64(int8(h[4]))
		s.calH[4] = float64(int8(h[5]))
		s.calH[5] = float64(uint8(h[6]))
		s.calH[6] = float64(int8(h[7]))
	}

	// Gas calibration
	gh1 := s.readReg(0xED, 1)
	gh2 := s.readReg(0xEB, 2)
	gh3 := s.readReg(0xEE, 1)
	rhr := s.readReg(0x02, 1)
	if gh1 != nil && gh2 != nil && gh3 != nil && rhr != nil {
		s.calGH[0] = float64(int8(gh1[0]))
		s.calGH[1] = float64(int16(uint16(gh2[1])<<8 | uint16(gh2[0])))
		s.calGH[2] = float64(int8(gh3[0]))
		s.resHR = rhr[0]
	}
}

func (s *bme680Sensor) configure() {
	// Humidity oversampling 2x
	s.writeReg(bme680CtrlHumReg, 0x02)
	// IIR filter size 3
	s.writeReg(bme680ConfigReg, 0x04)
	// Gas heater: calculate target resistance for 320°C, 150ms
	s.writeReg(bme680ResHeat0Reg, s.calcResHeat(320))
	s.writeReg(bme680GasWait0Reg, 0x59) // ~150ms
	// Enable gas, select heater profile 0
	s.writeReg(bme680CtrlGas1Reg, 0x10)
}

func (s *bme680Sensor) calcResHeat(target int) byte {
	// Simplified heater resistance calculation
	var1 := s.calGH[0]/16.0 + 49.0
	var2 := s.calGH[1]/32768.0*0.0005 + 0.00235
	var3 := s.calGH[2] / 1024.0
	var4 := var1 * (1.0 + var2*float64(target))
	var5 := var4 + var3*float64(s.resHR)
	return byte(3.4 * (var5*(4.0/3.0+float64(target)*(-0.01)) - 25))
}

func (s *bme680Sensor) Name() string { return "BME680" }

func (s *bme680Sensor) Read() sensorReading {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Set forced mode: temp 8x, press 4x oversampling + forced
	s.writeReg(bme680CtrlMeasReg, 0x54|0x01) // osrs_t=8x, osrs_p=4x, mode=forced
	time.Sleep(200 * time.Millisecond)

	data := s.readReg(bme680DataReg, 17)
	if data == nil {
		return nil
	}

	// Check if new data is available
	if data[0]&0x80 == 0 {
		return nil
	}

	// Raw ADC values
	pressADC := float64(uint32(data[2])<<12 | uint32(data[3])<<4 | uint32(data[4]>>4))
	tempADC := float64(uint32(data[5])<<12 | uint32(data[6])<<4 | uint32(data[7]>>4))
	humADC := float64(uint16(data[8])<<8 | uint16(data[9]))
	gasADC := float64(uint16(data[13])<<2 | uint16(data[14]>>6))
	gasRange := data[14] & 0x0F

	// Temperature compensation
	var1 := (tempADC/16384.0 - s.calT[0]/1024.0) * s.calT[1]
	var2 := ((tempADC/131072.0 - s.calT[0]/8192.0) *
		(tempADC/131072.0 - s.calT[0]/8192.0)) * s.calT[2] * 16.0
	tFine := var1 + var2
	temp := tFine / 5120.0

	// Pressure compensation
	var1 = tFine/2.0 - 64000.0
	var2 = var1 * var1 * s.calP[5] / 131072.0
	var2 += var1 * s.calP[4] * 2.0
	var2 = var2/4.0 + s.calP[3]*65536.0
	var1 = (s.calP[2]*var1*var1/16384.0 + s.calP[1]*var1) / 524288.0
	var1 = (1.0 + var1/32768.0) * s.calP[0]
	press := 0.0
	if var1 != 0 {
		press = 1048576.0 - pressADC
		press = (press - var2/4096.0) * 6250.0 / var1
		var1 = s.calP[8] * press * press / 2147483648.0
		var2 = press * s.calP[7] / 32768.0
		var3 := press / 256.0 * press / 256.0 * press / 256.0 * s.calP[9] / 131072.0
		press += (var1 + var2 + var3 + s.calP[6]*128.0) / 16.0
	}
	press /= 100.0 // Pa to hPa

	// Humidity compensation
	tempComp := tFine / 5120.0
	var1 = humADC - (s.calH[0]*16.0 + s.calH[2]/2.0*tempComp)
	var2 = var1 * (s.calH[1] / 262144.0) * (1.0 + s.calH[3]/16384.0*tempComp + s.calH[4]/1048576.0*tempComp*tempComp)
	var3 := s.calH[5] / 16384.0
	var4 := s.calH[6] / 2097152.0
	hum := var2 + (var3+var4*tempComp)*var2*var2
	if hum > 100.0 {
		hum = 100.0
	} else if hum < 0.0 {
		hum = 0.0
	}

	// Gas resistance
	gasRangeLUT := [16]float64{
		1, 1, 1, 1, 1, 0.99, 1, 0.992,
		1, 1, 0.998, 0.995, 1, 0.99, 1, 1,
	}
	var1 = 1340.0 + 5.0*gasRangeLUT[gasRange]
	var2 = var1 * float64(uint32(1)<<gasRange)
	gasRes := uint32(var1 * gasADC / var2)

	iaq := s.iaq.calculate(gasRes, hum)

	return sensorReading{
		"temperature": round(temp, 1),
		"humidity":    round(hum, 1),
		"pressure":    round(press, 2),
		"iaq":         iaq,
	}
}

func (s *bme680Sensor) ReadDiscovery() sensorReading {
	full := s.Read()
	if full == nil {
		return sensorReading{}
	}
	return sensorReading{
		"temp":  full["temperature"],
		"hum":   full["humidity"],
		"press": full["pressure"],
		"iaq":   full["iaq"],
	}
}

func (s *bme680Sensor) Close() {
	s.bus.Close()
}

// -- SCD30 Sensor ------------------------------------------------------------

const scd30Addr = 0x61

type scd30Sensor struct {
	dev *i2c.Dev
	bus i2c.BusCloser
	mu  sync.Mutex
}

func newSCD30(i2cBus int) *scd30Sensor {
	bus, err := i2creg.Open(fmt.Sprintf("/dev/i2c-%d", i2cBus))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to open I2C bus: %v\n", err)
		os.Exit(1)
	}
	dev := &i2c.Dev{Bus: bus, Addr: scd30Addr}

	s := &scd30Sensor{dev: dev, bus: bus}

	// Set measurement interval to 2 seconds
	s.writeCommand(0x4600, 2)
	time.Sleep(30 * time.Millisecond)

	// Start continuous measurement (ambient pressure 0 = default)
	s.writeCommand(0x0010, 0)
	time.Sleep(30 * time.Millisecond)

	return s
}

func (s *scd30Sensor) writeCommand(cmd, arg uint16) {
	argBytes := []byte{byte(arg >> 8), byte(arg)}
	crc := crc8(argBytes)
	buf := []byte{byte(cmd >> 8), byte(cmd), argBytes[0], argBytes[1], crc}
	s.dev.Tx(buf, nil)
}

func (s *scd30Sensor) dataReady() bool {
	read := make([]byte, 3)
	err := s.dev.Tx([]byte{0x02, 0x02}, read)
	if err != nil {
		return false
	}
	time.Sleep(30 * time.Millisecond)
	value := uint16(read[0])<<8 | uint16(read[1])
	return value == 1
}

func (s *scd30Sensor) readMeasurement() (co2, temp, hum float64, ok bool) {
	buf := make([]byte, 18)
	err := s.dev.Tx([]byte{0x03, 0x00}, buf)
	if err != nil {
		return 0, 0, 0, false
	}
	time.Sleep(30 * time.Millisecond)

	co2f, ok1 := extractFloat(buf[0:6])
	tempf, ok2 := extractFloat(buf[6:12])
	humf, ok3 := extractFloat(buf[12:18])
	if !ok1 || !ok2 || !ok3 {
		return 0, 0, 0, false
	}
	return float64(co2f), float64(tempf), float64(humf), true
}

func (s *scd30Sensor) Name() string { return "SCD30" }

func (s *scd30Sensor) Read() sensorReading {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.dataReady() {
		return nil
	}
	co2, temp, hum, ok := s.readMeasurement()
	if !ok {
		return nil
	}
	return sensorReading{
		"temperature": round(temp, 1),
		"humidity":    round(hum, 1),
		"co2":         round(co2, 1),
	}
}

func (s *scd30Sensor) ReadDiscovery() sensorReading {
	full := s.Read()
	if full == nil {
		return sensorReading{}
	}
	return sensorReading{
		"temp": full["temperature"],
		"hum":  full["humidity"],
		"co2":  full["co2"],
	}
}

func (s *scd30Sensor) Close() {
	s.bus.Close()
}

// -- Sensor Factory ----------------------------------------------------------

func createSensor(sensorType string, i2cBus int) sensor {
	switch sensorType {
	case "BME680":
		return newBME680(i2cBus)
	case "SCD30":
		return newSCD30(i2cBus)
	default:
		fmt.Fprintf(os.Stderr, "Error: Unknown sensor type '%s'.\n", sensorType)
		fmt.Fprintln(os.Stderr, "Supported: BME680, SCD30")
		os.Exit(1)
		return nil
	}
}
