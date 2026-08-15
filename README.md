# CSSIM — Control Systems Simulator

CSSIM is a didactic control-systems simulator integrated with Jupyter Notebook. It provides an interactive block-diagram editor, a Python simulation engine, and interactive time-domain plots.

Instalation tutorial: https://youtu.be/vRMpviLoTO0

## 1. Prerequisites

- Python 3.12 or a compatible version
- `pip`
- Git

## 2. Clone the repository

```bash
git clone https://github.com/mshoji-ufrj/cssim.git
cd cssim
```

## 3. Create and activate a virtual environment

Create the environment inside the project directory:

```bash
python -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Upgrade `pip` after activating the environment:

```bash
python -m pip install --upgrade pip
```

## 4. Install the dependencies

The dependency file contains pinned versions of the simulation, GUI, plotting, notebook, and monitoring packages:

```bash
python -m pip install -r requirements.txt
```

## 5. Open the main notebook

With the virtual environment active and the current directory set to the repository root, run:

```bash
jupyter notebook cssim_notebook.ipynb
```

The browser should open automatically. If it does not, open the URL printed in the terminal.

## 6. Use CSSIM

Run the notebook cells in order. The graphical interface can be opened without a predefined diagram:

```python
from cssim import open_gui

open_gui()
```

To preload one of the example diagrams, pass its path to `open_gui`:

```python
open_gui("diagrams/first_order_step.json")
```

The interface supports input, transfer-function, output, operation, gain, PID-controller, and text blocks. Parameters may contain numeric values or expressions that reference numeric variables defined in the notebook. The names `s` and `t` are reserved for the Laplace variable and time, respectively.

After assembling the diagram, set the simulation time and step size in the interface and use the **Run** button displayed below it. Example diagrams are available in the `diagrams/` directory.

