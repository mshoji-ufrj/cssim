# CSSIM — Control Systems Simulator

CSSIM is a didactic control-systems simulator integrated with Jupyter Notebook. It provides an interactive block-diagram editor, a Python simulation engine, and interactive time-domain plots.

## 1. Prerequisites

- Python 3.12 or a compatible version
- Git
- `pip`

## 2. Clone the repository

```bash
git clone https://github.com/mshoji-ufrj/cssim.git
cd cssim
```

## 3. Create and activate a virtual environment

Create the environment inside the project directory:

```bash
python3 -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Optionally, upgrade `pip` after activating the environment:

```bash
python -m pip install --upgrade pip
```

## 4. Install the dependencies

The dependency file contains pinned versions of the simulation, GUI, plotting, notebook, and monitoring packages:

```bash
python -m pip install -r requirements.txt
```

Jupyter Notebook is included in `requirements.txt`. To use JupyterLab instead, install it separately:

```bash
python -m pip install jupyterlab
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

## 7. PID derivative support

The PID block supports the `P`, `PI`, `PD`, and `PID` modes. Derivative action is implemented as a realizable filtered term with coefficient $N$:

$$
K_P\frac{T_Ds}{(T_D/N)s+1}.
$$

The default value is $N=100$. Therefore, `PD` and `PID` controllers use filtered derivative action rather than an ideal derivative. The current solver does not support ideal derivatives. Generic improper transfer functions, for which the numerator degree is greater than the denominator degree, are also unsupported by the `transfer_function` block.

## 8. Current scope

- Continuous-time, linear time-invariant systems modeled in the Laplace domain;
- arbitrary block-diagram topologies that can be represented in state space;
- multiple inputs and outputs;
- time-domain simulation and interactive plotting;
- proper transfer functions only;
- no discrete-time or robust-control support in the current version.
