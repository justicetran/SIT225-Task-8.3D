import os
import glob
import pandas as pd

# 1. Gather all CSV files
csv_paths = glob.glob("data/*.csv")

# 2. Extract timestamp from filename and sort chronologically
def extract_timestamp(filepath):
    filename = os.path.basename(filepath)
    # Extracts the YYYYMMDDHHMMSS part after the underscore
    parts = filename.replace(".csv", "").split("_")
    return parts[1] if len(parts) > 1 else filename

# Sort files by their actual capture time
csv_paths.sort(key=extract_timestamp)

records = []

# 3. Assign labels based on session timestamps
for filepath in csv_paths:
    filename = os.path.basename(filepath).replace(".csv", "")
    timestamp_str = extract_timestamp(filepath)
    
    # Check timestamp to assign the correct activity label
    if timestamp_str >= "20260920211750":
        activity = "Shaking"
    elif timestamp_str >= "20260920211334":
        activity = "Waving"
    else:
        activity = "Do Nothing"
        
    records.append({
        "filename": filename,
        "activity": activity
    })

# 4. Save clean annotation.csv
df = pd.DataFrame(records)
df.to_csv("annotation.csv", index=False)

print(f"Successfully generated annotation.csv with {len(df)} entries.")