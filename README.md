# CSSIM Setup Guide

Follow the steps below to prepare the environment, create an isolated virtualenv, install the dependencies, and open the notebook.

## 1. Prerequisites
- Python 3.12 (or compatible)
- Up-to-date `pip` (`python3 -m pip install --upgrade pip`)
- Git

## 2. Clone the repository
```bash
git clone https://github.com/mshoji-ufrj/cssim.git
cd cssim
```

## 3. Create and activate the virtualenv
Create a virtual environment inside the project folder:
```bash
python3 -m venv .venv
```
Activate the virtualenv (Linux/macOS):
```bash
source .venv/bin/activate
```
On Windows PowerShell:
```powershell
\.venv\Scripts\Activate.ps1
```

## 4. Install project dependencies
With the virtualenv active, install all required packages (version pinned) via `requirements.txt`:
```bash
pip install -r requirements.txt
```

## 5. Install Jupyter Notebook (if missing)
If the `jupyter notebook` command is not available, install it:
```bash
pip install notebook
```
(Optional) To use JupyterLab:
```bash
pip install jupyterlab
```

## 6. Open the main notebook
Still inside the virtualenv, start the Jupyter server and open the project notebook:
```bash
jupyter notebook cssim_notebook.ipynb
```
The browser should open automatically; if not, copy the URL printed in the terminal and open it manually.

## 7. Next steps
- Inside the notebook, run the cells in order to start the GUI (`open_gui(...)`) and explore the diagrams.
- Always keep the virtualenv activated before running scripts or notebooks to ensure the correct package versions are used.
