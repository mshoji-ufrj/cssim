import json
import os
import logging

from flask import Flask, request, jsonify, send_from_directory
import flask.cli as flask_cli
from threading import Thread

from cssim import run_simulation, set_parameters


app = Flask(__name__)

last_data_diagram = None
session_diagrams = {}
initial_diagram_path = None


def set_initial_diagram_path(path: str | None):
    global initial_diagram_path
    if path:
        initial_diagram_path = os.path.abspath(path)
    else:
        initial_diagram_path = None

@app.route('/')
def gui():
    return send_from_directory('.', 'gui.html')


@app.route('/initial-diagram', methods=['GET'])
def initial_diagram():
    if not initial_diagram_path:
        return jsonify({"status": "empty"})

    try:
        with open(initial_diagram_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return jsonify({
            "status": "error",
            "message": f"File not found: {initial_diagram_path}"
        }), 404
    except json.JSONDecodeError as exc:
        return jsonify({
            "status": "error",
            "message": f"Invalid JSON file: {exc}"
        }), 400
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc)
        }), 500

    return jsonify({"status": "ok", "data": data})

@app.route('/diagram-state', methods=['GET', 'POST'])
def diagram_state():
    global last_data_diagram

    session_id = request.args.get('session')

    if request.method == 'POST':
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify({
                "status": "error",
                "message": "Invalid or missing payload."
            }), 400
        if session_id:
            session_diagrams[session_id] = payload
        last_data_diagram = payload
        return jsonify({"status": "ok"})

    data = None
    if session_id:
        data = session_diagrams.get(session_id)
    if data is None:
        data = last_data_diagram
    if data is None:
        return jsonify({"status": "empty"}), 404

    return jsonify({"status": "ok", "data": data})

@app.route('/run', methods=['POST'])
def run():
    global last_data_diagram

    try:
        req = request.get_json()

        data_diagram = req.get("data")
        sim_time = float(req.get("sim_time", 10))
        step_size = float(req.get("step_size", 0.001))

        # ==== AUTO PARAM CAPTURE ====
        try:
            # function locals
            set_parameters(locals())
            # notebook namespace
            from IPython import get_ipython
            ip = get_ipython()
            if ip:
                user_ns = ip.user_ns
                numeric_params = {
                    k: float(v) for k, v in user_ns.items()
                    if k not in ('s', 't') and isinstance(v, (int, float))
                }
                set_parameters(numeric_params)
        except Exception:
            pass
        # =================================
        run_simulation(
            data_diagram,
            simulation_time=sim_time,
            step_size=step_size
        )

        last_data_diagram = data_diagram

        return jsonify({"status": "ok", "message": "Simulation completed."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask(port=8000, initial_diagram=None):
    if initial_diagram is not None:
        set_initial_diagram_path(initial_diagram)

    try:
        flask_cli.show_server_banner = lambda *args: None  # type: ignore
    except Exception:
        pass

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.logger.disabled = True

    app.run(port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

