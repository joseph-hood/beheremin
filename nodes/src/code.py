import time
import json
import board
import digitalio
import os
import wifi
import supervisor
import microcontroller
from ota import OTAServer

# Hard reboot automatically after a USB flash (soft reload) so boot.py can run
if supervisor.runtime.run_reason == supervisor.RunReason.AUTO_RELOAD:
    print("Auto-reload detected after flash. Hard rebooting...")
    time.sleep(0.5)
    microcontroller.reset()

# Initialize LED
try:
    led_pin = board.LED
except AttributeError:
    try:
        led_pin = board.IO15
    except AttributeError:
        led_pin = None

if led_pin:
    led = digitalio.DigitalInOut(led_pin)
    led.direction = digitalio.Direction.OUTPUT
else:
    led = None

print("Connecting to WiFi...")
wifi_boot_wait = 0
while not wifi.radio.ipv4_address:
    time.sleep(1)
    wifi_boot_wait += 1
    if wifi_boot_wait >= 60:
        print("WiFi connect timeout, rebooting...")
        microcontroller.reset()

print("Connected! IP:", wifi.radio.ipv4_address)

def apply_pending_wifi_update():
    try:
        with open("/wifi_update.json", "r") as f:
            update = json.load(f)
    except OSError:
        return  # No pending update — normal startup

    # Delete immediately so a failed attempt doesn't retry on next boot
    try:
        os.remove("/wifi_update.json")
    except Exception:
        pass

    new_ssid = update.get("ssid", "")
    new_pass = update.get("password", "")
    new_hub  = update.get("hub_ip", "")

    # Skip silently if nothing actually changed — hub always sends this file
    if (new_ssid == os.getenv("CIRCUITPY_WIFI_SSID", "") and
        new_pass == os.getenv("CIRCUITPY_WIFI_PASSWORD", "") and
        new_hub  == os.getenv("OTA_SERVER_IP", "")):
        return

    final_name = os.getenv("NODE_NAME", "UNKNOWN_NODE")

    wifi_changing = (new_ssid != os.getenv("CIRCUITPY_WIFI_SSID", "") or
                     new_pass != os.getenv("CIRCUITPY_WIFI_PASSWORD", ""))

    if wifi_changing:
        print("Testing new WiFi credentials:", new_ssid)
        try:
            wifi.radio.connect(new_ssid, new_pass)
        except Exception as e:
            print("WiFi connect error:", e)

        connected = False
        for _ in range(15):
            if wifi.radio.ipv4_address:
                connected = True
                break
            time.sleep(1)

        if not connected:
            print("New credentials failed — rebooting to restore old connection.")
            microcontroller.reset()

        print("New credentials verified. IP:", wifi.radio.ipv4_address)
    else:
        print("Updating hub_ip only:", new_hub)

    with open("/settings.toml", "w") as f:
        f.write(f'CIRCUITPY_WIFI_SSID = "{new_ssid}"\n')
        f.write(f'CIRCUITPY_WIFI_PASSWORD = "{new_pass}"\n')
        f.write(f'OTA_SERVER_IP = "{new_hub}"\n')
        f.write(f'NODE_NAME = "{final_name}"\n')

    print("settings.toml updated. Rebooting...")
    time.sleep(1)
    microcontroller.reset()

apply_pending_wifi_update()

node_name = os.getenv("NODE_NAME", "UNKNOWN_NODE")
server_ip = os.getenv("OTA_SERVER_IP")

# OTAServer owns the single SocketPool for this device
ota = None
ota_bound_ip = None
if server_ip:
    try:
        ota = OTAServer(server_ip=server_ip)
        ota.start()
        ota_bound_ip = str(wifi.radio.ipv4_address)
    except Exception as e:
        print("Failed to start OTA server:", e)
else:
    print("Warning: OTA_SERVER_IP not found. OTA disabled.")

def register():
    if not ota or not server_ip:
        return
    try:
        payload = {"name": node_name, "ip": str(wifi.radio.ipv4_address)}
        response = ota.requests.post(f"http://{server_ip}:3000/api/register", json=payload)
        print("Registered:", response.status_code)
        response.close()
    except Exception as e:
        print("Registration failed:", e)

register()

try:
    with open("/version.txt", "r") as f:
        print("Current Version:", f.read().strip())
except Exception:
    print("Version unknown.")

print(">>> UPDATED CODE V2 RUNNING <<<")
print("Blinking LED FASTER...")

REGISTER_INTERVAL = 30
WIFI_RECONNECT_TIMEOUT = 30
MAX_POLL_ERRORS = 20  # reboot if OTA server socket is stuck (~20s at 1s sleep)

last_register = time.monotonic()
consecutive_poll_errors = 0

while True:
    # WiFi watchdog: wait for natural reconnect before rebooting
    if not wifi.radio.ipv4_address:
        print("WiFi lost, waiting up to", WIFI_RECONNECT_TIMEOUT, "s...")
        for _ in range(WIFI_RECONNECT_TIMEOUT):
            time.sleep(1)
            if wifi.radio.ipv4_address:
                break

        if not wifi.radio.ipv4_address:
            print("WiFi did not recover, rebooting...")
            microcontroller.reset()

        new_ip = str(wifi.radio.ipv4_address)
        print("WiFi recovered:", new_ip)
        register()
        last_register = time.monotonic()
        consecutive_poll_errors = 0

        if new_ip != ota_bound_ip:
            # IP changed — OTA server is bound to the old address, need clean restart
            print("IP changed, rebooting for clean OTA server state...")
            time.sleep(1)
            microcontroller.reset()

    if ota:
        try:
            ota.poll()
            consecutive_poll_errors = 0
        except Exception as e:
            consecutive_poll_errors += 1
            print(f"OTA poll error ({consecutive_poll_errors}):", e)
            if consecutive_poll_errors >= MAX_POLL_ERRORS:
                print("OTA server stuck, rebooting...")
                microcontroller.reset()

    if led:
        led.value = not led.value

    if time.monotonic() - last_register >= REGISTER_INTERVAL:
        register()
        last_register = time.monotonic()

    time.sleep(1.0)
