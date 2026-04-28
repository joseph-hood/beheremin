import os
import json
import tomllib
import asyncio
import time
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="SensorNet Manager")

CONFIG_FILE = "nodes/nodes.json"
NETWORK_CONFIG_FILE = "config.toml"
WIFI_UPDATE_FILE = "nodes/src/wifi_update.json"

def sync_wifi_update():
    """Write nodes/src/wifi_update.json from config.toml so OTA always carries current credentials."""
    try:
        with open(NETWORK_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
        net = config.get("network", {})
        payload = {
            "ssid": net.get("wifi_ssid", ""),
            "password": net.get("wifi_password", ""),
            "hub_ip": net.get("hub_ip", ""),
        }
        with open(WIFI_UPDATE_FILE, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"Warning: could not sync wifi_update.json from config.toml: {e}")

sync_wifi_update()

# Runtime-only state — never persisted to disk
node_ips: dict[str, str] = {}             # name -> ip, populated from /api/register
nodes_updating: set[str] = set()          # names currently undergoing OTA
node_online_since: dict[str, float] = {}  # name -> monotonic time first seen online this session
node_first_seen: dict[str, float] = {}    # name -> monotonic time of first register after server start

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"nodes": []}

def save_config(config):
    # Only persist names — IPs are runtime state
    nodes_to_save = [{"name": n["name"]} for n in config.get("nodes", [])]
    with open(CONFIG_FILE, "w") as f:
        json.dump({"nodes": nodes_to_save}, f, indent=2)

@app.get("/api/info")
def get_info():
    try:
        with open(NETWORK_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
        net = config.get("network", {})
        return {"wifi_ssid": net.get("wifi_ssid", "unknown"), "hub_ip": net.get("hub_ip", "unknown")}
    except Exception:
        return {"wifi_ssid": "unknown", "hub_ip": "unknown"}

@app.get("/api/nodes")
def get_nodes():
    config = load_config()
    nodes = [
        {"name": n["name"], "ip": node_ips.get(n["name"])}
        for n in config.get("nodes", [])
    ]
    return {"nodes": nodes}

class RegisterRequest(BaseModel):
    name: str
    ip: str

@app.post("/api/register")
def register_node(req: RegisterRequest):
    node_ips[req.name] = req.ip
    if req.name not in node_first_seen:
        node_first_seen[req.name] = time.monotonic()

    config = load_config()
    nodes = config.get("nodes", [])
    if not any(n["name"] == req.name for n in nodes):
        nodes.append({"name": req.name})
        config["nodes"] = nodes
        save_config(config)

    return {"status": "registered", "node": req.name, "ip": req.ip}

class OtaRequest(BaseModel):
    names: list[str]

@app.post("/api/ota")
async def trigger_ota(req: OtaRequest):
    results = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for name in req.names:
            ip = node_ips.get(name)
            if not ip:
                results[name] = {"status": "error", "message": "No IP registered"}
                continue

            nodes_updating.add(name)
            try:
                response = await client.get(f"http://{ip}/update")
                results[name] = response.json()
            except Exception as e:
                results[name] = {"status": "error", "message": str(e)}
            finally:
                nodes_updating.discard(name)

    return {"status": "completed", "results": results}

@app.get("/api/health")
async def check_health():
    config = load_config()
    nodes = config.get("nodes", [])

    def uptime_pct(name: str, uptime_secs: int) -> float:
        first_seen = node_first_seen.get(name)
        if not first_seen:
            return 0.0
        elapsed = time.monotonic() - first_seen
        if elapsed <= 0:
            return 100.0
        return round(min(uptime_secs / elapsed, 1.0) * 100, 1)

    async def check_node(client: httpx.AsyncClient, name: str):
        now = time.monotonic()

        if name in nodes_updating:
            uptime = int(now - node_online_since[name]) if name in node_online_since else 0
            return name, {"status": "updating", "message": "OTA Update in Progress", "version": "—", "uptime": uptime, "uptime_pct": uptime_pct(name, uptime)}

        ip = node_ips.get(name)
        if not ip:
            node_online_since.pop(name, None)
            return name, {"status": "offline", "message": "Not yet registered", "uptime": 0, "uptime_pct": 0.0}

        # Retry once on transient errors before marking offline
        for attempt in range(2):
            try:
                response = await client.get(f"http://{ip}/health")
                if response.status_code == 200:
                    data = response.json()
                    if name not in node_online_since:
                        node_online_since[name] = now
                    # Prefer node-reported uptime (accurate to device boot); fall back to hub-tracked
                    uptime = data.get("uptime") if data.get("uptime") is not None else int(now - node_online_since[name])
                    return name, {
                        "status": "online",
                        "message": data.get("status", "ok"),
                        "version": data.get("version", "unknown"),
                        "uptime": uptime,
                        "uptime_pct": uptime_pct(name, uptime),
                        "ssid": data.get("ssid"),
                    }
                node_online_since.pop(name, None)
                return name, {"status": "error", "message": f"HTTP {response.status_code}", "version": "unknown", "uptime": 0, "uptime_pct": 0.0}
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                node_online_since.pop(name, None)
                msg = "Read timeout" if isinstance(e, httpx.ReadTimeout) else "Connection refused"
                return name, {"status": "offline", "message": msg, "uptime": 0, "uptime_pct": 0.0}
            except Exception as e:
                node_online_since.pop(name, None)
                return name, {"status": "offline", "message": str(e), "uptime": 0, "uptime_pct": 0.0}

        # Unreachable — the loop always returns on attempt 1 — but satisfies the type checker
        node_online_since.pop(name, None)
        return name, {"status": "offline", "message": "Unknown error", "uptime": 0, "uptime_pct": 0.0}

    async with httpx.AsyncClient(timeout=5.0) as client:
        pairs = await asyncio.gather(*[check_node(client, n["name"]) for n in nodes])

    return dict(pairs)

# Mount the src folder for OTA updates
app.mount("/src", StaticFiles(directory="nodes/src"), name="src")

# Mount frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=3000, reload=True)
