using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace DiashowApiDemo
{
    class Program
    {
        private static readonly HttpClient client = new HttpClient(
            new HttpClientHandler
            {
                ServerCertificateCustomValidationCallback = (_, _, _, _) => true
            });
        private const int ApiPort = 9134;

        static async Task<JObject> Api(string host, string key, string method, string path, object? body = null)
        {
            var url = $"https://{host}:{ApiPort}{path}";
            var request = new HttpRequestMessage(new HttpMethod(method), url);
            request.Headers.Add("X-Api-Key", key);

            if (body != null)
            {
                var json = JsonConvert.SerializeObject(body);
                request.Content = new StringContent(json, Encoding.UTF8, "application/json");
            }

            var response = await client.SendAsync(request);
            var content = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
            {
                throw new Exception($"API Error: {response.StatusCode} - {content}");
            }

            return JObject.Parse(content);
        }

        static async Task Main(string[] args)
        {
            if (args.Length < 3)
            {
                Console.WriteLine("Usage: dotnet run -- <display-ip> <filename> <api-key> [show-in-archive]");
                return;
            }

            string host = args[0];
            string filename = args[1];
            string key = args[2];
            string? targetShow = args.Length > 3 ? args[3] : null;

            if (!File.Exists(filename))
            {
                Console.WriteLine($"Error: File '{filename}' not found.");
                return;
            }

            // 1. Read and encode
            Console.WriteLine($"Reading '{filename}'...");
            byte[] fileBytes = File.ReadAllBytes(filename);
            string b64Data = Convert.ToBase64String(fileBytes);

            // 2. Upload
            Console.WriteLine($"Uploading to {host}:{ApiPort}...");
            string showName;
            try
            {
                var uploadResult = await Api(host, key, "POST", "/api/library/upload", new
                {
                    name = Path.GetFileName(filename),
                    data = b64Data
                });
                showName = uploadResult["name"]?.ToString() ?? Path.GetFileName(filename);
                Console.WriteLine($"Upload successful: {showName}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Upload failed: {ex.Message}");
                return;
            }

            // 3. Resolve name
            string startName = showName;
            if (startName.EndsWith(".ddl.json")) startName = startName.Substring(0, startName.Length - 9);
            else if (startName.EndsWith(".json")) startName = startName.Substring(0, startName.Length - 5);

            // 4. Stop current
            try { await Api(host, key, "POST", "/api/show/stop"); } catch { }

            // 5. Start
            Console.WriteLine($"Starting show '{startName}'...");
            try
            {
                var payload = new JObject { ["name"] = startName };
                if (targetShow != null) payload["show"] = targetShow;

                var result = await Api(host, key, "POST", "/api/show/start", payload);
                Console.WriteLine($"Playback started: {result["name"]}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Failed to start show: {ex.Message}");
                return;
            }

            Console.WriteLine("\nControls:  <- previous  |  -> next  |  c clear cache  |  q quit\n");

            while (true)
            {
                var keyInfo = Console.ReadKey(true);
                if (keyInfo.Key == ConsoleKey.LeftArrow)
                {
                    await Api(host, key, "POST", "/api/show/previous");
                    Console.WriteLine("<- previous");
                }
                else if (keyInfo.Key == ConsoleKey.RightArrow)
                {
                    await Api(host, key, "POST", "/api/show/next");
                    Console.WriteLine("-> next");
                }
                else if (keyInfo.Key == ConsoleKey.C)
                {
                    await Api(host, key, "POST", "/api/cache/clear");
                    Console.WriteLine("cache cleared");
                }
                else if (keyInfo.Key == ConsoleKey.Q)
                {
                    Console.WriteLine("Stopping show...");
                    await Api(host, key, "POST", "/api/show/stop");
                    break;
                }
            }
        }
    }
}
