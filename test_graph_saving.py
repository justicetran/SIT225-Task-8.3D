import os
import time
import threading
from datetime import datetime
import pandas as pd
import cv2
import plotly.graph_objects as go
from arduino_iot_cloud import ArduinoCloudClient
from credentials import DEVICE_ID, SECRET_KEY

# Storage setup
for folder in ["data", "graphs", "images"]:
    os.makedirs(folder, exist_ok=True)

curr_x, curr_y, curr_z = 0.0, 0.0, 0.0
has_data = False
window_samples = []
lock = threading.Lock()

def extract_val(val_obj):
    if hasattr(val_obj, 'value'):
        return float(val_obj.value)
    elif isinstance(val_obj, dict) and 'value' in val_obj:
        return float(val_obj['value'])
    try:
        return float(val_obj)
    except (ValueError, TypeError):
        return 0.0

def on_x(client, val):
    global curr_x, has_data
    curr_x = extract_val(val)
    has_data = True
    print(f"  [LIVE CLOUD UPDATE] X changed to: {curr_x:.3f}")

def on_y(client, val):
    global curr_y, has_data
    curr_y = extract_val(val)
    has_data = True
    print(f"  [LIVE CLOUD UPDATE] Y changed to: {curr_y:.3f}")

def on_z(client, val):
    global curr_z, has_data
    curr_z = extract_val(val)
    has_data = True
    print(f"  [LIVE CLOUD UPDATE] Z changed to: {curr_z:.3f}")

def start_cloud():
    client = ArduinoCloudClient(device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY)
    client.register("accelerometer_x", value=None, on_write=on_x)
    client.register("accelerometer_y", value=None, on_write=on_y)
    client.register("accelerometer_z", value=None, on_write=on_z)
    client.start()

def sampler():
    while True:
        time.sleep(0.2)  # Sample at 5 Hz
        if has_data:
            sample = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                'x': curr_x, 'y': curr_y, 'z': curr_z
            }
            with lock:
                window_samples.append(sample)

def capture_webcam(prefix):
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        for _ in range(5): cap.read()
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(f"images/{prefix}.jpg", frame)
    cap.release()

if __name__ == '__main__':
    print("=== STARTING PIPELINE TEST (3 WINDOWS = 30 SECONDS) ===")
    print("Connecting to Arduino Cloud... Move your phone now!")

    # Start Cloud & Sampler threads
    threading.Thread(target=start_cloud, daemon=True).start()
    threading.Thread(target=sampler, daemon=True).start()

    # Run for exactly 3 test windows
    for i in range(1, 4):
        print(f"\n--- Starting Window {i}/3 (Collecting data for 10 seconds) ---")
        time.sleep(10)

        with lock:
            samples_to_save = list(window_samples)
            window_samples.clear()

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix = f"test_{i}_{ts}"

        # 1. Save CSV
        df = pd.DataFrame(samples_to_save)
        df.to_csv(f"data/{prefix}.csv", index=False)
        print(f"  [1/3] CSV saved: data/{prefix}.csv ({len(df)} rows)")

        # 2. Save Webcam Image
        capture_webcam(prefix)
        print(f"  [2/3] Photo saved: images/{prefix}.jpg")

        # 3. Save PNG Graph
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['x'], mode='lines', name='X'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['y'], mode='lines', name='Y'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['z'], mode='lines', name='Z'))
        fig.update_layout(title=f"Test Graph {i}", xaxis_title="Time", yaxis_title="m/s²")
        
        try:
            fig.write_image(f"graphs/{prefix}.png")
            print(f"  [3/3] Graph saved: graphs/{prefix}.png")
        except Exception as e:
            print(f"  [3/3 GRAPH FAILED]: {e}")

    print("\n=== TEST COMPLETE ===")
    print("Check VS Code explorer to verify files in data/, images/, and graphs/.")