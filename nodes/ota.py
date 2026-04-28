import http.server
import socketserver
import json
import urllib.request
import os
import argparse
import threading

PORT = 8000

class OTAHandler(http.server.SimpleHTTPRequestHandler):

    def do_POST(self):

        if self.path == '/push':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                sensor_ips = data.get('ips', [])
                
                results = {}
                for ip in sensor_ips:
                    print(f"\n--- Pushing update to sensor {ip} ---")
                    try:
                        # Request the sensor to perform an update
                        req = urllib.request.Request(f"http://{ip}/update")
                        with urllib.request.urlopen(req, timeout=15) as response:
                            res_data = response.read().decode('utf-8')
                            res_json = json.loads(res_data)
                            results[ip] = res_json
                            print(f"Sensor {ip} replied successfully:")
                            print(f"  New Version: {res_json.get('new_version')}")
                            print(f"  Boot Out: {res_json.get('boot_out', '').strip()}")
                    except Exception as e:
                        print(f"Failed to update {ip}: {e}")
                        results[ip] = {"status": "error", "message": str(e)}

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "completed", "results": results}).encode('utf-8'))

            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():

    # Make sure we're serving from the directory containing 'src'
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with socketserver.TCPServer(("", PORT), OTAHandler) as httpd:

        print(f"OTA Laptop Server listening on port {PORT}")
        print(f"Serving files from: {os.getcwd()}")
        print(f"API Endpoint: POST http://localhost:{PORT}/push")
        print(f"Example payload: {{\"ips\": [\"192.168.1.50\", \"192.168.1.51\"]}}")
        try:
            httpd.serve_forever()
            
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.shutdown()

def run_oneshot(ips):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    httpd = socketserver.TCPServer(("", PORT), OTAHandler)
    
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    print(f"OTA Laptop Server started in one-shot mode on port {PORT}")
    print(f"Serving files from: {os.getcwd()}")
    
    results = {}
    for ip in ips:
        print(f"\n--- Pushing update to sensor {ip} ---")
        try:
            # Request the sensor to perform an update
            req = urllib.request.Request(f"http://{ip}/update")
            with urllib.request.urlopen(req, timeout=15) as response:
                res_data = response.read().decode('utf-8')
                res_json = json.loads(res_data)
                results[ip] = res_json
                print(f"Sensor {ip} replied successfully:")
                print(f"  New Version: {res_json.get('new_version')}")
                print(f"  Boot Out: {res_json.get('boot_out', '').strip()}")
        except Exception as e:
            print(f"Failed to update {ip}: {e}")
            results[ip] = {"status": "error", "message": str(e)}

    print("\n--- One-shot update complete ---")
    print(json.dumps(results, indent=2))
    
    httpd.shutdown()
    httpd.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OTA Laptop Server")
    parser.add_argument("--oneshot", nargs='+', help="IP addresses to update in one shot mode", default=[])
    args = parser.parse_args()
    
    if args.oneshot:
        run_oneshot(args.oneshot)
    else:
        run_server()
