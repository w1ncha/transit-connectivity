import pandas as pd
import os

TXT_DIR = "txt_data"
CSV_DIR = "csv_data"
DELIMITER = "," 

if not os.path.exists(CSV_DIR):
    os.makedirs(CSV_DIR)

for filename in os.listdir(TXT_DIR):
    if filename.endswith(".txt"):
        source_path = os.path.join(TXT_DIR, filename)
        target_path = os.path.join(CSV_DIR, filename.replace(".txt", ".csv"))
        
        df = pd.read_csv(source_path, sep=DELIMITER, index_col=None)
        df.to_csv(target_path, index=False)
        
        print(f"Converted: {filename}")