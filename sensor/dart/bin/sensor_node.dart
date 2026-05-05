/// DiashowDL Sensor Node — Dart CLI
///
/// Implements the DiashowDL Sensor Interface (see docs/sensor.md).
/// Supports BME680 (IAQ) or SCD30 (CO2) via I2C using dart_periphery.
///
/// - HTTPS REST API on port 9132
/// - UDP Discovery on port 9133
///
/// Usage:
///     cp config.example.json config.json
///     dart run bin/sensor_node.dart
import 'dart:convert';
import 'dart:io';

import 'package:dart_periphery/dart_periphery.dart';

// -- Ports (from sensor spec) ------------------------------------------------

const httpsPort = 9132;
const udpPort = 9133;

// -- Configuration -----------------------------------------------------------

Map<String, dynamic> loadConfig() {
  final file = File('config.json');
  if (!file.existsSync()) {
    stderr.writeln(
      'Error: config.json not found.\n'
      'Copy config.example.json to config.json and edit it.',
    );
    exit(1);
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

// -- Sensor Abstraction ------------------------------------------------------

sealed class Sensor {
  String get name;
  Map<String, dynamic>? read();

  Map<String, dynamic> readDiscovery() {
    final full = read();
    if (full == null) return {};
    return _toShortKeys(full);
  }

  Map<String, dynamic> _toShortKeys(Map<String, dynamic> full);

  void dispose();
}

class Bme680Sensor extends Sensor {
  final I2C _i2c;
  final BME680 _sensor;

  @override
  final String name = 'BME680';

  Bme680Sensor._(this._i2c, this._sensor);

  factory Bme680Sensor(int i2cBus) {
    final i2c = I2C(i2cBus);
    return Bme680Sensor._(i2c, BME680(i2c));
  }


  @override
  Map<String, dynamic>? read() {
    try {
      final r = _sensor.getValues();
      return {
        'temperature': _round(r.temperature, 1),
        'humidity': _round(r.humidity, 1),
        'pressure': _round(r.pressure, 2),
        'iaq': r.airQualityScore.round(),
      };
    } catch (e) {
      stderr.writeln('BME680 read error: $e');
      return null;
    }
  }

  @override
  Map<String, dynamic> _toShortKeys(Map<String, dynamic> full) => {
        'temp': full['temperature'],
        'hum': full['humidity'],
        'press': full['pressure'],
        'iaq': full['iaq'],
      };

  @override
  void dispose() => _i2c.dispose();
}

class Scd30Sensor extends Sensor {
  final I2C _i2c;
  final SCD30 _sensor;

  @override
  final String name = 'SCD30';

  Scd30Sensor._(this._i2c, this._sensor);

  factory Scd30Sensor(int i2cBus) {
    final i2c = I2C(i2cBus);
    return Scd30Sensor._(i2c, SCD30(i2c));
  }

  @override
  Map<String, dynamic>? read() {
    try {
      final r = _sensor.getValues();
      if (!r.available) return null;
      return {
        'temperature': _round(r.temperature, 1),
        'humidity': _round(r.humidity, 1),
        'co2': _round(r.co2, 1),
      };
    } catch (e) {
      stderr.writeln('SCD30 read error: $e');
      return null;
    }
  }

  @override
  Map<String, dynamic> _toShortKeys(Map<String, dynamic> full) => {
        'temp': full['temperature'],
        'hum': full['humidity'],
        'co2': full['co2'],
      };

  @override
  void dispose() => _i2c.dispose();
}

double _round(double value, int places) {
  final mod = _pow10(places);
  return (value * mod).roundToDouble() / mod;
}

double _pow10(int n) {
  var result = 1.0;
  for (var i = 0; i < n; i++) {
    result *= 10;
  }
  return result;
}

// -- Helpers -----------------------------------------------------------------

Future<String> getLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
    );
    for (final interface in interfaces) {
      for (final addr in interface.addresses) {
        if (!addr.isLoopback) return addr.address;
      }
    }
  } catch (_) {}
  return '127.0.0.1';
}

// -- UDP Discovery -----------------------------------------------------------

Future<void> startUdpDiscovery(Sensor sensor, String hostname) async {
  final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, udpPort);
  print('UDP discovery listening on port $udpPort');

  socket.listen((event) async {
    if (event != RawSocketEvent.read) return;
    final datagram = socket.receive();
    if (datagram == null) return;

    final msg = utf8.decode(datagram.data).trim();
    if (msg != 'DIASHOW_SCAN') return;

    final ip = await getLocalIp();
    final response = <String, dynamic>{
      'type': sensor.name,
      'host': hostname,
      'ip': ip,
      'port': httpsPort,
    };
    response.addAll(sensor.readDiscovery());

    final payload = utf8.encode(jsonEncode(response));
    socket.send(payload, datagram.address, datagram.port);
  });
}

// -- HTTPS REST API ----------------------------------------------------------

Future<void> startHttpsServer(
  Sensor sensor,
  String hostname,
  String apiKey,
  String certPath,
  String keyPath,
) async {
  final context = SecurityContext()
    ..useCertificateChain(certPath)
    ..usePrivateKey(keyPath);

  final server = await HttpServer.bindSecure(
    InternetAddress.anyIPv4,
    httpsPort,
    context,
  );
  print('HTTPS server on port $httpsPort');

  await for (final request in server) {
    if (request.headers.value('X-Api-Key') != apiKey) {
      request.response.statusCode = HttpStatus.unauthorized;
      await request.response.close();
      continue;
    }

    final data = sensor.read();
    if (data == null) {
      request.response
        ..statusCode = HttpStatus.serviceUnavailable
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({'error': 'Sensor read failed'}));
      await request.response.close();
      continue;
    }

    final response = <String, dynamic>{
      'sensor': sensor.name,
      'host': hostname,
    };
    response.addAll(data);

    request.response
      ..headers.contentType = ContentType.json
      ..write(jsonEncode(response));
    await request.response.close();
  }
}

// -- Main --------------------------------------------------------------------

Future<void> main() async {
  print('--- DiashowDL Sensor Node (Dart) ---');

  final config = loadConfig();
  final apiKey = config['api_key'] as String;
  final sensorType = (config['sensor'] as String? ?? 'BME680').toUpperCase();
  final hostname =
      (config['hostname'] as String? ?? '').isEmpty
          ? Platform.localHostname
          : config['hostname'] as String;
  final i2cBus = config['i2c_bus'] as int? ?? 1;
  final sslCert = config['ssl_cert'] as String? ?? 'cert.pem';
  final sslKey = config['ssl_key'] as String? ?? 'key.pem';

  final Sensor sensor;
  switch (sensorType) {
    case 'BME680':
      sensor = Bme680Sensor(i2cBus);
    case 'SCD30':
      sensor = Scd30Sensor(i2cBus);
    default:
      stderr.writeln("Error: Unknown sensor type '$sensorType'.");
      stderr.writeln('Supported: BME680, SCD30');
      exit(1);
  }

  print('Sensor: ${sensor.name} on /dev/i2c-$i2cBus');
  print('Hostname: $hostname');

  try {
    await startUdpDiscovery(sensor, hostname);
    await startHttpsServer(sensor, hostname, apiKey, sslCert, sslKey);
  } finally {
    sensor.dispose();
  }
}
