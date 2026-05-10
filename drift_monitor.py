import pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
import os
import time

def main():
    print("=== RouteCraft Data Drift Monitor ===")
    
    csv_path = "data/Banglore_traffic_Dataset.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found. Please ensure you have downloaded the dataset.")
        return

    print(f"Loading traffic dataset from {csv_path}...")
    df = pd.read_csv(csv_path)

    # For demonstration, we split the data to simulate a "reference" (training) set 
    # and a "current" (production) set. In a real MLOps pipeline, 'current' 
    # would be freshly collected data.
    split_idx = int(len(df) * 0.8)
    reference_data = df.iloc[:split_idx].copy()
    current_data = df.iloc[split_idx:].copy()

    # Artificially inject some drift into the current data to make the report interesting
    # (e.g., increase travel time index to simulate worse real-world traffic)
    if 'Travel Time Index' in current_data.columns:
        print("Injecting artificial drift for demonstration (Travel Time Index + 15%)...")
        current_data['Travel Time Index'] = current_data['Travel Time Index'] * 1.15

    print(f"Reference data shape: {reference_data.shape}")
    print(f"Current data shape:   {current_data.shape}")

    print("\nGenerating Data Drift Report using Evidently AI...")
    t0 = time.time()
    
    # Define the report
    report = Report(metrics=[DataDriftPreset()])
    
    # Run the drift analysis
    report.run(reference_data=reference_data, current_data=current_data)
    
    # Save the report as an interactive HTML file
    report_path = "evidently_drift_report.html"
    report.save_html(report_path)
    
    print(f"Drift analysis complete in {round(time.time() - t0, 2)}s.")
    print(f"Report saved to: {os.path.abspath(report_path)}")
    print(f"\nOpen {report_path} in your web browser to view the interactive drift metrics.")

if __name__ == "__main__":
    main()
