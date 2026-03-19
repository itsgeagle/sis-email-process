import warnings
warnings.warn(
    "This script is deprecated. Incident CSV lookup is now handled by app.py.",
    DeprecationWarning,
    stacklevel=1,
)

import pandas as pd

file_path = "inputs/incident.csv"

try:
    # Attempt to read with a fallback encoding
    data = pd.read_csv(file_path, encoding="ISO-8859-1", on_bad_lines="warn")
    print("File loaded successfully.")

    # Check for unexpected nulls
    print(data.isnull().sum())  # Look for missing values per column

    # Identify rows where "short_description" is missing
    missing_descriptions = data[data["short_description"].isnull()]
    print(missing_descriptions)

    # Check for duplicate entries
    duplicates = data.duplicated()
    print(f"Duplicate rows: {duplicates.sum()}")



except Exception as e:
    print(f"Error loading the file: {e}")
