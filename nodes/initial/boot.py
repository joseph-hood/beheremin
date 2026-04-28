import storage

print("Sensor Node Booting...")
storage.remount("/", readonly=False, disable_concurrent_write_protection=True)
