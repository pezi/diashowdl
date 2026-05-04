import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:path/path.dart' as p;

const int apiPort = 9134;

final _client = IOClient(
  HttpClient()..badCertificateCallback = (_, __, ___) => true,
);

Future<dynamic> api(String host, String key, String method, String path,
    {Map<String, dynamic>? body}) async {
  final url = Uri.parse('https://$host:$apiPort$path');
  final headers = {
    'X-Api-Key': key,
    'Content-Type': 'application/json',
  };

  http.Response response;
  if (method == 'GET') {
    response = await _client.get(url, headers: headers);
  } else {
    response =
        await _client.post(url, headers: headers, body: jsonEncode(body ?? {}));
  }

  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('API Error: ${response.statusCode} - ${response.body}');
  }

  return jsonDecode(response.body);
}

void main(List<String> args) async {
  if (args.length < 3) {
    print(
        'Usage: dart api_demo.dart <display-ip> <filename> <api-key> [show-in-archive]');
    exit(1);
  }

  final host = args[0];
  final filename = args[1];
  final key = args[2];
  final targetShow = args.length > 3 ? args[3] : null;

  final file = File(filename);
  if (!file.existsSync()) {
    print("Error: File '$filename' not found.");
    exit(1);
  }

  // 1. Read and encode file
  print("Reading '$filename'...");
  final bytes = await file.readAsBytes();
  final b64Data = base64Encode(bytes);

  // 2. Upload to library
  print("Uploading to $host:$apiPort...");
  String showName;
  try {
    final uploadResult =
        await api(host, key, 'POST', '/api/library/upload', body: {
      'name': p.basename(filename),
      'data': b64Data,
    });
    print("Upload successful: ${uploadResult['name']}");
    showName = uploadResult['name'];
  } catch (e) {
    print("Upload failed: $e");
    exit(1);
  }

  // 3. Prepare name for start command
  var startName = showName;
  if (startName.endsWith('.ddl.json')) {
    startName = startName.substring(0, startName.length - 9);
  } else if (startName.endsWith('.json')) {
    startName = startName.substring(0, startName.length - 5);
  }

  // 4. Stop current show
  print("Ensuring server is ready...");
  try {
    await api(host, key, 'POST', '/api/show/stop');
  } catch (_) {}

  // 5. Start playback
  var msg = "Starting show '$startName'";
  if (targetShow != null) msg += " (internal show: $targetShow)";
  print("$msg...");

  try {
    final payload = {'name': startName};
    if (targetShow != null) payload['show'] = targetShow;

    final result =
        await api(host, key, 'POST', '/api/show/start', body: payload);
    final actualName =
        result['name'] ?? "${result['archive']} [${result['show']}]";
    print("Playback started: $actualName");
  } catch (e) {
    print("Failed to start show: $e");
    exit(1);
  }

  print('\nControls:  <- previous  |  -> next  |  c clear cache  |  q quit\n');

  // Keypress handling
  stdin.echoMode = false;
  stdin.lineMode = false;

  await for (final List<int> data in stdin) {
    if (data.isEmpty) continue;

    final char = String.fromCharCode(data[0]);

    if (data.length >= 3 && data[0] == 27 && data[1] == 91) {
      // Escape sequence: ESC [ A/B/C/D
      final direction = data[2];
      if (direction == 68) {
        // Left
        await api(host, key, 'POST', '/api/show/previous');
        stdout.write('<- previous\n');
      } else if (direction == 67) {
        // Right
        await api(host, key, 'POST', '/api/show/next');
        stdout.write('-> next\n');
      }
    } else if (char.toLowerCase() == 'c') {
      await api(host, key, 'POST', '/api/cache/clear');
      stdout.write('cache cleared\n');
    } else if (char.toLowerCase() == 'q' || data[0] == 3) {
      // q or Ctrl+C
      // ignore: avoid_print
      print("Stopping show...");
      await api(host, key, 'POST', '/api/show/stop');
      print("Done.");
      exit(0);
    }
  }
}
