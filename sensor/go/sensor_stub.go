//go:build !linux

package main

type stubSensor struct {
	name string
}

func (s *stubSensor) Name() string            { return s.name }
func (s *stubSensor) Read() sensorReading     { return nil }
func (s *stubSensor) ReadDiscovery() sensorReading { return sensorReading{} }
func (s *stubSensor) Close()                  {}

func createSensor(sensorType string, i2cBus int) sensor {
	switch sensorType {
	case "BME680", "SCD30":
	default:
		panic("Unknown sensor type: " + sensorType)
	}
	return &stubSensor{name: sensorType}
}
