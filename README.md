

Reflash
-------

https://circuitpython.org/board/lolin_s2_mini/


Update Initial State
--------------------

```shell
python .\nodes\flash.py D --name NODENAME
```

Run SensorNet
----------------

```shell
python.exe c:/dev/sensornet/app.py
```

http://localhost:3000/


Wifi
----

wifi_ssid = "BigMagicEero"
wifi_password = "deadbeef10"
hub_ip = "192.168.6.20"


Open writable
-------------

Connect via USB serial (Thonny, Mu, PuTTY — any terminal at 115200), press Ctrl+C to stop code.py and get the REPL, then paste:

```shell
f = open("/boot.py", "w")
f.write('import storage\nprint("Sensor Node Booting...")\nstorage.remount("/", readonly=False, disable_concurrent_write_protection=True)\n')
f.close()
import microcontroller
microcontroller.reset()
```
