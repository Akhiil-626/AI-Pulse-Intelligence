import json
import subprocess
import sys

def main():
    with open("workflows/nvd_historical_backfill.json", encoding="utf-8") as f:
        data = json.load(f)
    wf = data[0] if isinstance(data, list) else data

    code_nodes = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code"]
    print(f"Validating {len(code_nodes)} Code nodes via Node.js vm.Script (inside async function wrapper)...")

    for n in code_nodes:
        name = n["name"]
        code = n["parameters"]["jsCode"]
        wrapped_code = f"async function n8nNodeRunner($input, $) {{\n{code}\n}}"
        js_tester = f"""
const vm = require('vm');
const code = {json.dumps(wrapped_code)};
try {{
    new vm.Script(code);
    console.log('SYNTAX OK: {name}');
}} catch (e) {{
    console.error('SYNTAX ERROR in {name}:', e.message);
    process.exit(1);
}}
"""
        res = subprocess.run(["node", "-e", js_tester], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error in {name}:\n{res.stderr}")
            sys.exit(1)
        else:
            print(res.stdout.strip())

    print("\nAll Code nodes passed JavaScript syntax verification!")

if __name__ == "__main__":
    main()
