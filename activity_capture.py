import os
import time
import threading
import base64
from datetime import datetime

import cv2
import pandas as pd
import plotly.graph_objects as go

from dash import Dash, dcc, html
from dash.dependencies import Input, Output

from arduino_iot_cloud import ArduinoCloudClient
from credentials import DEVICE_ID, SECRET_KEY


# ============================================================
# 1. PROJECT FOLDERS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
IMAGE_DIR = os.path.join(BASE_DIR, "images")
GRAPH_DIR = os.path.join(BASE_DIR, "graphs")

# Create folders if they do not already exist.
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(GRAPH_DIR, exist_ok=True)


# ============================================================
# 2. GLOBAL VARIABLES
# ============================================================

# Stores incoming accelerometer samples.
sensor_data = []

# Latest accelerometer values.
latest_x = None
latest_y = None
latest_z = None

# Prevents conflicts between the Cloud thread and
# the 10-second capture thread.
data_lock = threading.Lock()

# Number of completed 10-second windows.
capture_count = 0

# Latest files.
latest_csv = "Waiting..."
latest_image = "Waiting..."
latest_graph = "Waiting..."


# ============================================================
# 3. ADD SENSOR SAMPLE
# ============================================================

def add_sensor_sample():
    """
    Add one accelerometer sample when X, Y and Z
    values are available.
    """
    global latest_x, latest_y, latest_z

    if latest_x is None or latest_y is None or latest_z is None:
        return

    sample = {
        "timestamp": datetime.now(),
        "x": latest_x,
        "y": latest_y,
        "z": latest_z
    }

    with data_lock:
        sensor_data.append(sample)


# ============================================================
# 4. ARDUINO CLOUD CALLBACKS
# ============================================================

def on_x_changed(client, value):
    global latest_x
    try:
        latest_x = float(value)
        add_sensor_sample()
    except (TypeError, ValueError):
        print("Invalid X value:", value)


def on_y_changed(client, value):
    global latest_y
    try:
        latest_y = float(value)
        add_sensor_sample()
    except (TypeError, ValueError):
        print("Invalid Y value:", value)


def on_z_changed(client, value):
    global latest_z
    try:
        latest_z = float(value)
        add_sensor_sample()
    except (TypeError, ValueError):
        print("Invalid Z value:", value)


# ============================================================
# 5. CONNECT TO ARDUINO IOT CLOUD
# ============================================================

def start_arduino_cloud():
    print()
    print("=" * 60)
    print("CONNECTING TO ARDUINO IOT CLOUD")
    print("=" * 60)

    try:
        client = ArduinoCloudClient(
            device_id=DEVICE_ID,
            username=DEVICE_ID,
            password=SECRET_KEY
        )

        client.register("accelerometer_x", value=None, on_write=on_x_changed)
        client.register("accelerometer_y", value=None, on_write=on_y_changed)
        client.register("accelerometer_z", value=None, on_write=on_z_changed)

        print("Arduino Cloud connected successfully.")
        print("Listening for accelerometer data...")
        print()

        client.start()

    except Exception as error:
        print()
        print("=" * 60)
        print("ARDUINO CLOUD CONNECTION ERROR")
        print("=" * 60)
        print(error)
        print("=" * 60)


# ============================================================
# 6. CREATE AND SAVE PNG GRAPH (ASYNC EXPORT)
# ============================================================

def _export_png_background(figure, png_path):
    """Background helper to render PNG without blocking the capture loop."""
    try:
        figure.write_image(
            png_path,
            width=1200,
            height=700,
            scale=2
        )
        print()
        print("PNG graph saved:")
        print(png_path)
    except Exception as error:
        print()
        print("PNG export failed/skipped:", error)


def create_graph(dataframe, base_filename):
    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["x"],
            mode="lines",
            name="X",
            line=dict(color="#1f77b4", width=2)
        )
    )

    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["y"],
            mode="lines",
            name="Y",
            line=dict(color="#ff7f0e", width=2)
        )
    )

    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["z"],
            mode="lines",
            name="Z",
            line=dict(color="#2ca02c", width=2)
        )
    )

    figure.update_layout(
        title=dict(
            text="Smartphone Accelerometer Data - " + base_filename,
            font=dict(size=18, color="#2c3e50")
        ),
        xaxis_title="Timestamp",
        yaxis_title="Acceleration",
        template="plotly_white",
        hovermode="x unified",
        legend_title="Axis",
        margin=dict(l=40, r=40, t=60, b=40)
    )

    png_path = os.path.join(GRAPH_DIR, base_filename + ".png")

    # Launch static PNG creation in a background thread so it cannot block capture
    threading.Thread(
        target=_export_png_background,
        args=(figure, png_path),
        daemon=True
    ).start()

    return figure, png_path


# ============================================================
# 7. CAPTURE WEBCAM IMAGE
# ============================================================

def capture_webcam_image(base_filename):
    image_path = os.path.join(IMAGE_DIR, base_filename + ".jpg")

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print()
        print("WARNING: Could not open webcam.")
        print()
        return None

    time.sleep(1)
    success, frame = camera.read()
    camera.release()

    if not success:
        print()
        print("WARNING: Could not capture webcam image.")
        print()
        return None

    cv2.imwrite(image_path, frame)

    print()
    print("Webcam image saved:")
    print(image_path)

    return image_path


# ============================================================
# 8. PROCESS ONE 10-SECOND WINDOW
# ============================================================

def process_10_second_window(window_data):
    global capture_count
    global latest_csv
    global latest_image
    global latest_graph

    if len(window_data) == 0:
        print()
        print("No accelerometer data received.")
        print("No files created for this window.")
        print()
        return

    capture_count += 1
    timestamp_string = datetime.now().strftime("%Y%m%d%H%M%S")
    base_filename = str(capture_count) + "_" + timestamp_string

    print()
    print("=" * 60)
    print("PROCESSING 10-SECOND WINDOW #" + str(capture_count))
    print("=" * 60)

    dataframe = pd.DataFrame(window_data)
    dataframe = dataframe[["timestamp", "x", "y", "z"]]

    csv_path = os.path.join(DATA_DIR, base_filename + ".csv")
    dataframe.to_csv(csv_path, index=False)

    latest_csv = os.path.relpath(csv_path, BASE_DIR)

    print()
    print("CSV saved:")
    print(csv_path)

    image_path = capture_webcam_image(base_filename)

    if image_path is not None:
        latest_image = os.path.relpath(image_path, BASE_DIR)
    else:
        latest_image = "Webcam capture failed"

    try:
        figure, png_path = create_graph(dataframe, base_filename)
        latest_graph = os.path.relpath(png_path, BASE_DIR)
    except Exception as error:
        print()
        print("ERROR CREATING GRAPH:")
        print(error)
        print()
        latest_graph = "Graph creation failed"

    print()
    print("Number of samples:", len(dataframe))
    print("X range:", round(dataframe["x"].min(), 3), "to", round(dataframe["x"].max(), 3))
    print("Y range:", round(dataframe["y"].min(), 3), "to", round(dataframe["y"].max(), 3))
    print("Z range:", round(dataframe["z"].min(), 3), "to", round(dataframe["z"].max(), 3))
    print()
    print("10-second window completed.")
    print("=" * 60)
    print()


# ============================================================
# 9. CONTINUOUS 10-SECOND CAPTURE LOOP
# ============================================================

def capture_loop():
    global sensor_data

    print()
    print("=" * 60)
    print("10-SECOND CAPTURE LOOP STARTED")
    print("=" * 60)
    print()

    while True:
        time.sleep(10)

        with data_lock:
            window_data = sensor_data.copy()
            sensor_data.clear()

        process_10_second_window(window_data)


# ============================================================
# 10. DASH APPLICATION (Styled Layout)
# ============================================================

app = Dash(__name__)
app.title = "SIT225 Week 8.3D Accelerometer Monitor"

app.layout = html.Div(
    style={
        "fontFamily": "Segoe UI, Tahoma, Geneva, Verdana, sans-serif",
        "backgroundColor": "#f4f7f6",
        "minHeight": "100vh",
        "padding": "30px",
        "color": "#333333"
    },
    children=[
        # Main Header Card
        html.Div(
            style={
                "backgroundColor": "white",
                "padding": "25px",
                "borderRadius": "10px",
                "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.05)",
                "marginBottom": "25px",
                "textAlign": "center"
            },
            children=[
                html.H1(
                    "SIT225 Week 8.3D",
                    style={"color": "#2c3e50", "marginBottom": "5px", "fontSize": "28px"}
                ),
                html.H2(
                    "Smartphone Accelerometer Monitor & Capture Dashboard",
                    style={"color": "#7f8c8d", "fontSize": "18px", "fontWeight": "normal"}
                )
            ]
        ),

        # Status & File Info Grid Container
        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gap": "20px",
                "marginBottom": "25px"
            },
            children=[
                # Live Status Card
                html.Div(
                    style={
                        "backgroundColor": "white",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.05)"
                    },
                    children=[
                        html.H3("Live System Status", style={"color": "#2c3e50", "marginTop": "0", "fontSize": "16px"}),
                        html.Div(
                            id="status",
                            style={"fontSize": "15px", "color": "#34495e", "lineHeight": "1.6"}
                        )
                    ]
                ),
                # File Registry Card
                html.Div(
                    style={
                        "backgroundColor": "white",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.05)"
                    },
                    children=[
                        html.H3("Latest Generated Artifacts", style={"color": "#2c3e50", "marginTop": "0", "fontSize": "16px"}),
                        html.Div(
                            id="file_status",
                            style={"fontSize": "15px", "color": "#34495e"}
                        )
                    ]
                )
            ]
        ),

        # Graph Container Card
        html.Div(
            style={
                "backgroundColor": "white",
                "padding": "20px",
                "borderRadius": "10px",
                "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.05)",
                "marginBottom": "25px"
            },
            children=[
                dcc.Graph(
                    id="accelerometer_graph",
                    style={"height": "500px"}
                )
            ]
        ),

        # Webcam Image Card Container
        html.Div(
            style={
                "backgroundColor": "white",
                "padding": "25px",
                "borderRadius": "10px",
                "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.05)",
                "textAlign": "center"
            },
            children=[
                html.H2(
                    "Latest Webcam Snapshot",
                    style={"color": "#2c3e50", "fontSize": "20px", "marginBottom": "15px"}
                ),
                html.Div(
                    id="webcam_container",
                    style={"display": "flex", "justifyContent": "center", "alignItems": "center"}
                )
            ]
        ),

        # Background Interval Timer
        dcc.Interval(
            id="dashboard_interval",
            interval=1000,
            n_intervals=0
        )
    ]
)


# ============================================================
# 11. DASHBOARD CALLBACK
# ============================================================

@app.callback(
    [
        Output("accelerometer_graph", "figure"),
        Output("status", "children"),
        Output("file_status", "children"),
        Output("webcam_container", "children")
    ],
    [
        Input("dashboard_interval", "n_intervals")
    ]
)
def update_dashboard(n_intervals):
    csv_files = [
        filename for filename in os.listdir(DATA_DIR)
        if filename.lower().endswith(".csv")
    ]

    if len(csv_files) == 0:
        empty_figure = go.Figure()
        empty_figure.update_layout(
            title="Waiting for accelerometer data...",
            xaxis_title="Timestamp",
            yaxis_title="Acceleration",
            template="plotly_white"
        )

        empty_file_div = html.Div([
            html.P("CSV: No files yet", style={"margin": "5px 0"}),
            html.P("Image: No files yet", style={"margin": "5px 0"}),
            html.P("Graph: No files yet", style={"margin": "5px 0"})
        ])

        return (
            empty_figure,
            "Awaiting initial 10-second data accumulation window...",
            empty_file_div,
            html.Div("Waiting for webcam capture...", style={"color": "#95a5a6", "fontStyle": "italic"})
        )

    csv_files.sort()
    newest_csv = csv_files[-1]
    csv_path = os.path.join(DATA_DIR, newest_csv)

    try:
        dataframe = pd.read_csv(csv_path)
        dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"])
    except Exception as error:
        empty_figure = go.Figure()
        return (
            empty_figure,
            "Error reading CSV: " + str(error),
            newest_csv,
            html.Div("Error loading webcam image.")
        )

    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["x"],
            mode="lines",
            name="X",
            line=dict(color="#1f77b4", width=2)
        )
    )
    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["y"],
            mode="lines",
            name="Y",
            line=dict(color="#ff7f0e", width=2)
        )
    )
    figure.add_trace(
        go.Scatter(
            x=dataframe["timestamp"],
            y=dataframe["z"],
            mode="lines",
            name="Z",
            line=dict(color="#2ca02c", width=2)
        )
    )

    figure.update_layout(
        title=dict(
            text="Latest 10-Second Accelerometer Window (" + newest_csv + ")",
            font=dict(size=18, color="#2c3e50")
        ),
        xaxis_title="Timestamp",
        yaxis_title="Acceleration",
        template="plotly_white",
        hovermode="x unified"
    )

    image_filename = os.path.splitext(newest_csv)[0] + ".jpg"
    image_path = os.path.join(IMAGE_DIR, image_filename)

    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode()

        image_display = html.Img(
            src="data:image/jpeg;base64," + encoded_image,
            style={
                "width": "600px",
                "maxWidth": "100%",
                "height": "auto",
                "borderRadius": "8px",
                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"
            }
        )
    else:
        image_display = html.Div(
            "Matching webcam image not available.",
            style={"color": "#e74c3c", "fontStyle": "italic"}
        )

    status_text = html.Div([
        html.P("Status: Actively monitoring sensor stream", style={"margin": "5px 0", "fontWeight": "600", "color": "#27ae60"}),
        html.P(f"Completed 10-Second Windows: {capture_count}", style={"margin": "5px 0"}),
        html.P(f"Samples in Current Window: {len(dataframe)}", style={"margin": "5px 0"})
    ])

    png_filename = os.path.splitext(newest_csv)[0] + ".png"

    file_text = html.Div([
        html.P(f"📄 CSV Data File: {newest_csv}", style={"margin": "5px 0", "color": "#2980b9"}),
        html.P(f"📷 Snapshot Image: {image_filename}", style={"margin": "5px 0", "color": "#2980b9"}),
        html.P(f"📈 Graph Image: {png_filename}", style={"margin": "5px 0", "color": "#2980b9"})
    ])

    return (
        figure,
        status_text,
        file_text,
        image_display
    )


# ============================================================
# 12. START PROGRAM
# ============================================================

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("SIT225 WEEK 8.3D ACTIVITY CAPTURE")
    print("=" * 60)
    print()
    print("Project folder:", BASE_DIR)
    print("Data folder:", DATA_DIR)
    print("Images folder:", IMAGE_DIR)
    print("Graphs folder:", GRAPH_DIR)
    print()
    print("=" * 60)

    # Start Arduino Cloud Thread.
    cloud_thread = threading.Thread(
        target=start_arduino_cloud,
        daemon=True
    )
    cloud_thread.start()

    # Start 10-Second Capture Loop Thread.
    capture_thread = threading.Thread(
        target=capture_loop,
        daemon=True
    )
    capture_thread.start()

    # Start Dash.
    print()
    print("=" * 60)
    print("DASHBOARD STARTING")
    print("=" * 60)
    print()
    print("Open this address in your browser:")
    print("http://127.0.0.1:8050/")
    print()
    print("Keep this terminal running.")
    print("Press CTRL+C to stop the program.")
    print()

    app.run(
        debug=False,
        host="127.0.0.1",
        port=8050
    )