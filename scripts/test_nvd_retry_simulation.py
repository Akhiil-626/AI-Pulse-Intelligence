import json
import subprocess
import sys

# Load the exact jsCode from Validate & Slice Batches
with open("workflows/nvd_historical_backfill.json", encoding="utf-8") as f:
    data = json.load(f)
wf = data[0] if isinstance(data, list) else data

val_node = next(n for n in wf["nodes"] if n["name"] == "Validate & Slice Batches")
val_code = val_node["parameters"]["jsCode"]

simulation_runner = f"""
const vm = require('vm');

const code = {json.dumps(val_code)};

function runValidateSlice(httpItem, lastWaitContext) {{
  const sandbox = {{
    $input: {{
      item: {{ json: httpItem }}
    }},
    $: (nodeName) => {{
      if (nodeName === 'Rate Limit Wait') {{
        return {{
          last: () => ({{ json: lastWaitContext }})
        }};
      }}
      throw new Error(`Unexpected node reference: ${{nodeName}}`);
    }},
    Error: Error,
    Date: Date,
    Array: Array,
    Math: Math,
    typeof: (x) => typeof x
  }};

  const script = new vm.Script(`
    (function() {{
      ${{code}}
    }})()
  `);
  const ctx = vm.createContext(sandbox);
  return script.runInContext(ctx);
}}

console.log("=== RUNNING RETRY & FAILURE TESTS ===");

const initialContext = {{
  config: {{
    pipeline_id: 'nvd_dry_run_7d',
    rate_limit_seconds: 6,
    page_size: 2000
  }},
  state: {{
    pipeline_id: 'nvd_dry_run_7d',
    start_date: '2026-10-25T00:00:00.000Z',
    end_date: '2026-11-01T00:00:00.000Z',
    current_offset: 2000,
    last_page: 1,
    total_records_ingested: 2000,
    expected_updated_at: '2026-11-05T12:00:00.000Z'
  }},
  fetch_params: {{
    pubStartDate: '2026-10-25T00:00:00.000Z',
    pubEndDate: '2026-11-01T00:00:00.000Z',
    startIndex: 2000,
    resultsPerPage: 2000
  }},
  retry_count: 0
}};

// Test 1: HTTP 429 Retry Sequence and Backoff
console.log("1. Testing HTTP 429 Retry Sequence (1st, 2nd, 3rd retry)...");
let ctx = {{ ...initialContext }};

// Attempt 1 -> Retry 1
let res = runValidateSlice({{ statusCode: 429 }}, ctx);
if (res[0].json.action !== 'retry') throw new Error("Expected action 'retry'");
if (res[0].json.retry_count !== 1) throw new Error("Expected retry_count 1");
if (res[0].json.wait_seconds !== 6) throw new Error("Expected wait_seconds 6 for retry 1");
if (res[0].json.fetch_params.startIndex !== 2000) throw new Error("Offset corrupted in retry 1");
console.log("   - Retry 1 OK: retry_count=1, wait_seconds=6s, offset preserved=2000");

// Attempt 2 -> Retry 2
ctx = {{ ...ctx, retry_count: 1 }};
res = runValidateSlice({{ statusCode: 429 }}, ctx);
if (res[0].json.action !== 'retry') throw new Error("Expected action 'retry'");
if (res[0].json.retry_count !== 2) throw new Error("Expected retry_count 2");
if (res[0].json.wait_seconds !== 12) throw new Error("Expected wait_seconds 12 for retry 2");
console.log("   - Retry 2 OK: retry_count=2, wait_seconds=12s, offset preserved=2000");

// Attempt 3 -> Retry 3
ctx = {{ ...ctx, retry_count: 2 }};
res = runValidateSlice({{ statusCode: 429 }}, ctx);
if (res[0].json.action !== 'retry') throw new Error("Expected action 'retry'");
if (res[0].json.retry_count !== 3) throw new Error("Expected retry_count 3");
if (res[0].json.wait_seconds !== 24) throw new Error("Expected wait_seconds 24 for retry 3");
console.log("   - Retry 3 OK: retry_count=3, wait_seconds=24s, offset preserved=2000");

// Attempt 4 -> Exhaustion (Failure)
ctx = {{ ...ctx, retry_count: 3 }};
try {{
  runValidateSlice({{ statusCode: 429 }}, ctx);
  throw new Error("Should have thrown exhaustion error on 4th 429");
}} catch (e) {{
  if (!e.message.includes("Maximum retries (3) exhausted")) {{
    throw new Error(`Unexpected error message: ${{e.message}}`);
  }}
  console.log("   - Exhaustion OK: Threw expected error after 3 retries ->", e.message);
}}

// Test 2: HTTP 503 Server Error Retry and Exhaustion
console.log("2. Testing HTTP 503 Server Error...");
ctx = {{ ...initialContext, retry_count: 0 }};
res = runValidateSlice({{ statusCode: 503 }}, ctx);
if (res[0].json.action !== 'retry' || res[0].json.retry_count !== 1 || res[0].json.wait_seconds !== 6) {{
  throw new Error("HTTP 503 retry 1 failed");
}}
console.log("   - HTTP 503 Retry 1 OK: retry_count=1, wait_seconds=6s");

ctx = {{ ...ctx, retry_count: 3 }};
try {{
  runValidateSlice({{ statusCode: 503 }}, ctx);
  throw new Error("Should have thrown exhaustion error on 503");
}} catch (e) {{
  if (!e.message.includes("Maximum retries (3) exhausted")) throw e;
  console.log("   - HTTP 503 Exhaustion OK ->", e.message);
}}

// Test 3: HTTP 403 Immediate Halt
console.log("3. Testing HTTP 403 Immediate Halt...");
try {{
  runValidateSlice({{ statusCode: 403 }}, initialContext);
  throw new Error("Should have thrown immediate halt error on 403");
}} catch (e) {{
  if (!e.message.includes("HTTP 403 Forbidden") || !e.message.includes("Stopped safely without retry")) {{
    throw new Error(`Unexpected error message on 403: ${{e.message}}`);
  }}
  console.log("   - HTTP 403 Halt OK: Zero retries ->", e.message);
}}

// Test 4: Other Non-2xx (HTTP 400)
console.log("4. Testing HTTP 400 Bad Request Halt...");
try {{
  runValidateSlice({{ statusCode: 400 }}, initialContext);
  throw new Error("Should have thrown error on 400");
}} catch (e) {{
  if (!e.message.includes("unexpected HTTP 400") || !e.message.includes("without retry")) {{
    throw new Error(`Unexpected error message on 400: ${{e.message}}`);
  }}
  console.log("   - HTTP 400 Halt OK: Zero retries ->", e.message);
}}

// Test 5: HTTP 200 Success after Retry
console.log("5. Testing HTTP 200 Success after retry...");
ctx = {{ ...initialContext, retry_count: 2 }};
const mockSuccessBody = {{
  totalResults: 2001,
  startIndex: 2000,
  resultsPerPage: 2000,
  vulnerabilities: [
    {{
      cve: {{
        id: "CVE-2026-9999",
        published: "2026-10-30T10:00:00.000Z",
        descriptions: [{{ lang: "en", value: "Test CVE description" }}]
      }}
    }}
  ]
}};
res = runValidateSlice({{ statusCode: 200, body: mockSuccessBody }}, ctx);
if (res[0].json.action !== 'proceed') throw new Error("Expected action 'proceed'");
if (res[0].json.is_empty_window !== false) throw new Error("Expected is_empty_window false");
if (res[0].json.record.id !== "CVE-2026-9999") throw new Error("Record id mismatch");
if (res[0].json._page_state.current_offset !== 2001) throw new Error("Next offset should be 2001");
if (res[0].json._page_state.last_page !== 2) throw new Error("Last page should be 2");
if (res[0].json._page_state.total_records_ingested !== 2001) throw new Error("Total records should be 2001");
console.log("   - HTTP 200 Success OK: Sliced 1 record, advanced offset to 2001, page to 2.");

console.log("ALL RETRY AND FAILURE SIMULATION TESTS PASSED SUCCESSFULLY!");
"""

res = subprocess.run(["node", "-e", simulation_runner], capture_output=True, text=True)
if res.returncode != 0:
    print("SIMULATION TEST FAILED:")
    print(res.stderr)
    sys.exit(1)
else:
    print(res.stdout)
