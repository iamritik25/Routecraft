# 🚀 Setup & Installation Guide

RouteCraft is designed to be "portable" with a local virtual environment. This guide covers how to set up the system from scratch.

## 📋 Prerequisites

- Python **3.10 to 3.12**
- Git
- Windows (Recommended for `.bat` scripts) or Linux/macOS

---

## ⚡ Quick Start (Windows)

1. **One-Click Install**:
   ```bat
   setup.bat
   ```
   This creates a `.venv` folder, installs dependencies, and initializes your `.env` file.

2. **Start the Server**:
   ```bat
   run.bat
   ```
   Access the UI at `http://127.0.0.1:5000`.

---

## 🧪 Manual Installation

If you prefer to set up manually or are on Linux/macOS:

1. **Create Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # .venv\Scripts\activate   # Windows
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize Config**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to set your `TRAFFIC_MODEL_TYPE` (default is `sklearn`).

---

## 🤖 Model Training

The repository does not include pre-trained models due to file size. You must train them locally before the ML features will activate:

```bash
# Train all models (LightGBM, sklearn, PyTorch)
python train_traffic_model.py
```
This will generate `.pkl` and `.pt` files in the `models/` directory.

---

## 🔄 Running Airflow (Optional)

To enable automated cache warming and model retraining:

1. **Setup Airflow**:
   ```bat
   airflow_setup.bat
   ```

2. **Start Airflow Components**:
   In two separate terminals:
   ```bat
   # Terminal 1
   airflow scheduler
   
   # Terminal 2
   airflow webserver
   ```
   Access the Airflow UI at `http://127.0.0.1:8080`.

---

## 🧪 Running Tests

Ensure your changes haven't broken the routing logic:

```bash
python -m pytest
```
The test suite covers surge pricing, Dijkstra logic, ETA confidence intervals, and the A/B testing backend.
