import sys
from arduino_iot_cloud import ArduinoCloudClient
from credentials import DEVICE_ID, SECRET_KEY

def on_x_changed(client, value):
    print(f"[LIVE] Accelerometer X: {value}")

def on_y_changed(client, value):
    print(f"[LIVE] Accelerometer Y: {value}")

def on_z_changed(client, value):
    print(f"[LIVE] Accelerometer Z: {value}")

if __name__ == "__main__":
    print("Connecting to Arduino IoT Cloud...")
    
    # Initialize the client using Device ID and Secret Key as password
    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        username=DEVICE_ID,
        password=SECRET_KEY
    )

    # Register variables and callbacks
    client.register("accelerometer_x", value=None, on_write=on_x_changed)
    client.register("accelerometer_y", value=None, on_write=on_y_changed)
    client.register("accelerometer_z", value=None, on_write=on_z_changed)

    # Start loop
    try:
        client.start()
    except KeyboardInterrupt:
        print("\nStopping cloud client.")
        sys.exit(0)