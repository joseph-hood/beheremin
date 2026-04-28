import os
import time
import wifi
import socketpool
import json
from adafruit_httpserver import Server, Request, Response, GET
import adafruit_requests
import ssl

class OTAServer:
    def __init__(self, server_ip, server_port=3000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.pool = socketpool.SocketPool(wifi.radio)
        self.server = Server(self.pool, debug=False)
        self.requests = adafruit_requests.Session(self.pool, ssl.create_default_context())
        self.should_reset = False
        self.start_time = time.monotonic()

        @self.server.route("/health", GET)
        def health_handler(request: Request):
            version = "unknown"
            try:
                with open("/version.txt", "r") as f:
                    version = f.read().strip()
            except Exception:
                pass
            uptime = int(time.monotonic() - self.start_time)
            ssid = "unknown"
            try:
                ssid = wifi.radio.ap_info.ssid
            except Exception:
                pass
            return Response(request, json.dumps({"status": "ok", "version": version, "uptime": uptime, "ssid": ssid}), content_type="application/json")
        
        @self.server.route("/update", GET)
        def update_handler(request: Request):
            try:
                print(f"Update triggered from {self.server_ip}:{self.server_port}")
                # Download version.txt
                version_url = f"http://{self.server_ip}:{self.server_port}/src/version.txt"
                print(f"Fetching {version_url}...")
                resp = self.requests.get(version_url)
                new_version = resp.text.strip()
                resp.close()
                print(f"Downloaded version.txt: {new_version}")
                
                # Download boot.py
                boot_url = f"http://{self.server_ip}:{self.server_port}/src/boot.py"
                print(f"Fetching {boot_url}...")
                resp = self.requests.get(boot_url)
                new_boot = resp.text
                resp.close()
                print("Downloaded boot.py.")

                # Download code.py
                code_url = f"http://{self.server_ip}:{self.server_port}/src/code.py"
                print(f"Fetching {code_url}...")
                resp = self.requests.get(code_url)
                new_code = resp.text
                resp.close()
                print("Downloaded code.py.")

                # Download ota.py
                ota_url = f"http://{self.server_ip}:{self.server_port}/src/ota.py"
                print(f"Fetching {ota_url}...")
                resp = self.requests.get(ota_url)
                new_ota = resp.text
                resp.close()
                print("Downloaded ota.py.")

                # Optionally download wifi_update.json if present on the hub
                wifi_update_data = None
                try:
                    wifi_url = f"http://{self.server_ip}:{self.server_port}/src/wifi_update.json"
                    resp = self.requests.get(wifi_url)
                    if resp.status_code == 200:
                        wifi_update_data = resp.text
                        print("Downloaded wifi_update.json.")
                    resp.close()
                except Exception:
                    pass  # Not present — skip silently

                # Save files
                print("Writing /version.txt...")
                with open("/version.txt", "w") as f:
                    f.write(new_version)
                
                print("Writing /boot.py...")
                with open("/boot.py", "w") as f:
                    f.write(new_boot)
                    
                print("Writing /code.py...")
                with open("/code.py", "w") as f:
                    f.write(new_code)

                print("Writing /ota.py...")
                with open("/ota.py", "w") as f:
                    f.write(new_ota)

                if wifi_update_data:
                    print("Writing /wifi_update.json...")
                    with open("/wifi_update.json", "w") as f:
                        f.write(wifi_update_data)

                print("Writing complete.")

                # Verify version
                verified_version = "unknown"
                try:
                    with open("/version.txt", "r") as f:
                        verified_version = f.read().strip()
                except Exception as e:
                    print("Error verifying version:", e)
                
                print(f"Verified version on device: {verified_version}")

                boot_out = ""
                try:
                    with open("/boot_out.txt", "r") as f:
                        boot_out = f.read()
                except Exception as e:
                    boot_out = str(e)

                res_data = {
                    "status": "success",
                    "new_version": verified_version,
                    "boot_out": boot_out
                }
                
                self.should_reset = True
                return Response(request, json.dumps(res_data), content_type="application/json")
                
            except Exception as e:
                print("OTA Error:", e)
                err_data = {"status": "error", "message": str(e)}
                return Response(request, json.dumps(err_data), content_type="application/json")

    def start(self):
        self.server.start(str(wifi.radio.ipv4_address), 80)
        print(f"Listening for OTA on http://{wifi.radio.ipv4_address}:80/update")

    def poll(self):
        self.server.poll()
        if self.should_reset:
            time.sleep(1)
            import microcontroller
            print("Rebooting to apply update...")
            microcontroller.reset()
