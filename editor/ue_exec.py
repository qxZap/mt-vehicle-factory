"""Run Python in the open Unreal editor via its built-in remote execution.

    python ue_exec.py "<code>"      or      python ue_exec.py -f script.py
"""
import sys
import time

import os
UE = os.environ.get("UE_ROOT", r"C:\Program Files\Epic Games\UE_5.5")   # your engine install
sys.path.insert(0, os.path.join(UE, r"Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"))
import remote_execution as re_

code = open(sys.argv[2], encoding="utf-8").read() if sys.argv[1] == "-f" else sys.argv[1]
rx = re_.RemoteExecution()
rx.start()
try:
    for _ in range(50):
        if rx.remote_nodes:
            break
        time.sleep(0.1)
    if not rx.remote_nodes:
        sys.exit("no editor found (Remote Execution enabled? editor open?)")
    rx.open_command_connection(rx.remote_nodes[0]["node_id"])
    r = rx.run_command(code, unattended=True, exec_mode=re_.MODE_EXEC_FILE)
    for o in r.get("output", []):
        print(o["output"], end="" if o["output"].endswith("\n") else "\n")
    if not r.get("success"):
        print("FAILED:", r.get("result"))
        sys.exit(1)
finally:
    rx.stop()
