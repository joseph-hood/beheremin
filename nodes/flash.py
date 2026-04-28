import sys
import shutil
import os
import argparse
import tomllib

def flash(drive_letter, node_name=None):

    if not drive_letter.endswith(":") and not drive_letter.endswith(":\\"):
        drive_letter = drive_letter + ":"
        
    if not drive_letter.endswith("\\"):
        drive_letter = drive_letter + "\\"
    
    if not os.path.exists(drive_letter):
        print(f"Error: Drive {drive_letter} not found. Please make sure the device is plugged in and the drive letter is correct.")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.dirname(__file__))
    config_file = os.path.join(base_dir, "config.toml")
    if not os.path.exists(config_file):
        print(f"Error: Config file not found at {config_file}")
        sys.exit(1)

    with open(config_file, "rb") as f:
        config = tomllib.load(f)

    network = config.get("network", {})
    ssid = network.get("wifi_ssid", "")
    password = network.get("wifi_password", "")
    hub_ip = network.get("hub_ip", "")

    initial_dir = os.path.join(os.path.dirname(__file__), "initial")
    
    if not os.path.exists(initial_dir):
        print("Error: 'initial' folder not found.")
        sys.exit(1)

    print(f"Flashing files from {initial_dir} to {drive_letter}...")
    
    for item in os.listdir(initial_dir):
        s = os.path.join(initial_dir, item)
        d = os.path.join(drive_letter, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
            print(f"Copied directory: {item}/")
        else:
            if item == "settings.toml":
                continue # We generate this dynamically from config.toml
            else:
                shutil.copy2(s, d)
                print(f"Copied file: {item}")
            
    # Write settings.toml dynamically
    settings_dest = os.path.join(drive_letter, "settings.toml")
    with open(settings_dest, "w") as f:
        f.write(f'CIRCUITPY_WIFI_SSID = "{ssid}"\n')
        f.write(f'CIRCUITPY_WIFI_PASSWORD = "{password}"\n')
        f.write(f'OTA_SERVER_IP = "{hub_ip}"\n')
        if node_name:
            f.write(f'NODE_NAME = "{node_name}"\n')
    print(f"Generated and wrote: settings.toml (added NODE_NAME={node_name})")

    print("\nFlashing complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flash sensor node")
    parser.add_argument("drive", nargs="?", default="D:", help="Drive letter of the sensor")
    parser.add_argument("--name", help="Unique name for the sensor node (e.g. NODE1)")
    
    args = parser.parse_args()
    flash(args.drive, args.name)
