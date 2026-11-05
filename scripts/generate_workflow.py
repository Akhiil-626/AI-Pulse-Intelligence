import json
import os

workflow = {
    "name": "NVD Historical Backfill",
    "id": "1QWWV6LogiG0Mcig",
    "nodes": [
        {
            "parameters": {},
            "id": "node_manual_trigger",
            "name": "When clicking ‘Execute workflow’",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [100, 300]
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "cfg_pipeline_id",
                            "name": "config.pipeline_id",
                            "value": "nvd_dry_run_7d",
                            "type": "string"
                        },
                        {
                            "id": "cfg_start_date",
                            "name": "config.initial_start_date",
                            "value": "2026-10-25T00:00:00.000Z",
                            "type": "string"
                        },
                        {
                            "id": "cfg_end_date",
                            "name": "config.target_end_date",
                            "value": "2026-11-01T00:00:00.000Z",
                            "type": "string"
                        },
                        {
                            "id": "cfg_window_days",
                            "name": "config.window_days",
                            "value": 7,
                            "type": "number"
                        },
                        {
                            "id": "cfg_page_size",
                            "name": "config.page_size",
                            "value": 2000,
                            "type": "number"
                        },
                        {
                            "id": "cfg_batch_size",
                            "name": "config.batch_size",
                            "value": 250,
                            "type": "number"
                        },
                        {
                            "id": "cfg_has_api_key",
                            "name": "config.has_nvd_api_key",
                            "value": False,
                            "type": "boolean"
                        },
                        {
                            "id": "cfg_rate_limit",
                            "name": "config.rate_limit_seconds",
                            "value": 6,
                            "type": "number"
                        },
                        {
                            "id": "cfg_api_base_url",
                            "name": "config.ingestion_api_base_url",
                            "value": "http://host.docker.internal:8001",
                            "type": "string"
                        }
                    ]
                },
                "options": {}
            },
            "id": "node_workflow_config",
            "name": "Workflow Config",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.5,
            "position": [320, 300]
        },
        {
            "parameters": {
                "method": "GET",
                "url": "={{ $json.config.ingestion_api_base_url }}/api/v1/checkpoint/{{ $json.config.pipeline_id }}",
                "options": {}
            },
            "id": "node_get_checkpoint",
            "name": "Get Checkpoint",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [540, 300]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": ""
                    },
                    "conditions": [
                        {
                            "id": "cond_init",
                            "leftValue": "={{ $json.initialized }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node_route_initialized",
            "name": "Route Initialized",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [760, 300]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $('Workflow Config').item.json.config.ingestion_api_base_url }}/api/v1/checkpoint/{{ $('Workflow Config').item.json.config.pipeline_id }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({\n  start_date: $('Workflow Config').item.json.config.initial_start_date,\n  end_date: $('Workflow Config').item.json.config.target_end_date,\n  current_offset: 0,\n  last_page: 0,\n  total_records_ingested: 0,\n  status: 'in_progress'\n}) }}",
                "options": {}
            },
            "id": "node_register_initial",
            "name": "Register Initial Checkpoint",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [980, 440]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const input = $input.item.json;\n"
                    "const cp = input.checkpoint || input;\n"
                    "const config = $('Workflow Config').item.json.config;\n\n"
                    "const state = {\n"
                    "  pipeline_id: cp.pipeline_id || config.pipeline_id,\n"
                    "  start_date: cp.start_date || config.initial_start_date,\n"
                    "  end_date: cp.end_date || config.target_end_date,\n"
                    "  current_offset: cp.current_offset !== undefined && cp.current_offset !== null ? cp.current_offset : 0,\n"
                    "  last_page: cp.last_page !== undefined && cp.last_page !== null ? cp.last_page : 0,\n"
                    "  total_records_ingested: cp.total_records_ingested !== undefined && cp.total_records_ingested !== null ? cp.total_records_ingested : 0,\n"
                    "  status: cp.status || 'in_progress',\n"
                    "  expected_updated_at: cp.updated_at || null\n"
                    "};\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    config: config,\n"
                    "    state: state\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_merge_initial",
            "name": "Merge Initial Context",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1200, 300]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const state = $input.item.json.state;\n"
                    "const config = $input.item.json.config;\n\n"
                    "const isCompleted = state.status === 'completed' || (new Date(state.start_date).getTime() >= new Date(config.target_end_date).getTime());\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    config: config,\n"
                    "    state: state,\n"
                    "    retry_count: 0,\n"
                    "    wait_seconds: config.rate_limit_seconds || 6,\n"
                    "    is_completed: isCompleted,\n"
                    "    fetch_params: {\n"
                    "      pubStartDate: state.start_date,\n"
                    "      pubEndDate: state.end_date,\n"
                    "      startIndex: state.current_offset,\n"
                    "      resultsPerPage: config.page_size\n"
                    "    }\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_prepare_fetch_state",
            "name": "Prepare Fetch State",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1420, 300]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": ""
                    },
                    "conditions": [
                        {
                            "id": "cond_completed",
                            "leftValue": "={{ $json.is_completed }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node_check_completed",
            "name": "Check Completed",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1640, 300]
        },
        {
            "parameters": {},
            "id": "node_stop_completed",
            "name": "Stop: Already Completed",
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [1860, 180]
        },
        {
            "parameters": {
                "resume": "timeInterval",
                "amount": "={{ $json.wait_seconds || $json.config.rate_limit_seconds || 6 }}",
                "unit": "seconds"
            },
            "id": "node_rate_limit_wait",
            "name": "Rate Limit Wait",
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [1860, 420]
        },
        {
            "parameters": {
                "method": "GET",
                "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {
                            "name": "pubStartDate",
                            "value": "={{ $json.fetch_params.pubStartDate }}"
                        },
                        {
                            "name": "pubEndDate",
                            "value": "={{ $json.fetch_params.pubEndDate }}"
                        },
                        {
                            "name": "startIndex",
                            "value": "={{ $json.fetch_params.startIndex }}"
                        },
                        {
                            "name": "resultsPerPage",
                            "value": "={{ $json.fetch_params.resultsPerPage }}"
                        }
                    ]
                },
                "options": {
                    "response": {
                        "response": {
                            "neverError": True,
                            "fullResponse": True
                        }
                    },
                    "timeout": 300000
                }
            },
            "id": "node_fetch_nvd",
            "name": "Fetch NVD Page",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [2080, 420]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const httpItem = $input.item.json;\n"
                    "const reqContext = $('Rate Limit Wait').last().json;\n"
                    "const state = reqContext.state;\n"
                    "const config = reqContext.config;\n"
                    "const fetchParams = reqContext.fetch_params;\n"
                    "const currentRetryCount = reqContext.retry_count || 0;\n\n"
                    "const statusCode = httpItem.statusCode || 200;\n\n"
                    "// 1. HTTP 403: halt immediately without retry\n"
                    "if (statusCode === 403) {\n"
                    "  throw new Error(\"NVD API HTTP 403 Forbidden: Potential rate limit block, WAF restriction, or missing API key. Stopped safely without retry.\");\n"
                    "}\n\n"
                    "// 2. HTTP 429 and HTTP 5xx: maximum 3 retries with exponential backoff\n"
                    "const isRetryable = (statusCode === 429) || (statusCode >= 500 && statusCode < 600);\n"
                    "if (isRetryable) {\n"
                    "  if (currentRetryCount >= 3) {\n"
                    "    throw new Error(`NVD API HTTP ${statusCode}: Maximum retries (3) exhausted. Halting safely without advancing checkpoint.`);\n"
                    "  }\n\n"
                    "  const nextRetryCount = currentRetryCount + 1;\n"
                    "  const baseDelay = config.rate_limit_seconds || 6;\n"
                    "  // Exponential backoff: retry 1 -> 6s, retry 2 -> 12s, retry 3 -> 24s\n"
                    "  const backoffSeconds = Math.max(baseDelay, baseDelay * Math.pow(2, nextRetryCount - 1));\n\n"
                    "  return [{\n"
                    "    json: {\n"
                    "      action: 'retry',\n"
                    "      retry_count: nextRetryCount,\n"
                    "      wait_seconds: backoffSeconds,\n"
                    "      status_code: statusCode,\n"
                    "      config: config,\n"
                    "      state: state,\n"
                    "      fetch_params: fetchParams\n"
                    "    }\n"
                    "  }];\n"
                    "}\n\n"
                    "// 3. Other non-2xx responses: halt safely without retry\n"
                    "if (statusCode < 200 || statusCode >= 300) {\n"
                    "  throw new Error(`NVD API unexpected HTTP ${statusCode}: Halting safely without retry or advancing checkpoint.`);\n"
                    "}\n\n"
                    "// 4. HTTP 200 OK: page processing and normalization\n"
                    "const body = httpItem.body || httpItem;\n"
                    "const totalResults = typeof body.totalResults === 'number' ? body.totalResults : 0;\n"
                    "const startIndex = typeof body.startIndex === 'number' ? body.startIndex : 0;\n"
                    "const resultsPerPage = typeof body.resultsPerPage === 'number' ? body.resultsPerPage : config.page_size;\n"
                    "const vulnerabilities = Array.isArray(body.vulnerabilities) ? body.vulnerabilities : [];\n"
                    "const actualCount = vulnerabilities.length;\n\n"
                    "if (actualCount > 0 && startIndex !== state.current_offset) {\n"
                    "  throw new Error(`NVD pagination offset mismatch: requested ${state.current_offset}, received startIndex ${startIndex}.`);\n"
                    "}\n"
                    "if (actualCount > resultsPerPage) {\n"
                    "  throw new Error(`NVD pagination count overflow: received ${actualCount} records exceeding resultsPerPage ${resultsPerPage}.`);\n"
                    "}\n\n"
                    "const nextOffset = state.current_offset + actualCount;\n"
                    "const isWindowExhausted = (actualCount === 0) || (actualCount < config.page_size) || (nextOffset >= totalResults);\n\n"
                    "if (actualCount === 0) {\n"
                    "  return [{\n"
                    "    json: {\n"
                    "      action: 'proceed',\n"
                    "      is_empty_window: true,\n"
                    "      total_results: totalResults,\n"
                    "      actual_count: 0,\n"
                    "      state: state,\n"
                    "      config: config\n"
                    "    }\n"
                    "  }];\n"
                    "}\n\n"
                    "const nextPageState = {\n"
                    "  pipeline_id: state.pipeline_id,\n"
                    "  start_date: state.start_date,\n"
                    "  end_date: state.end_date,\n"
                    "  current_offset: nextOffset,\n"
                    "  last_page: state.last_page + 1,\n"
                    "  total_records_ingested: state.total_records_ingested + actualCount,\n"
                    "  expected_updated_at: state.expected_updated_at,\n"
                    "  actual_count: actualCount,\n"
                    "  total_results: totalResults,\n"
                    "  is_window_exhausted: isWindowExhausted\n"
                    "};\n\n"
                    "const nowIso = new Date().toISOString();\n"
                    "return vulnerabilities.map((v, idx) => {\n"
                    "  const cve = v.cve || {};\n"
                    "  const descObj = (cve.descriptions || []).find(d => d.lang === 'en');\n"
                    "  const desc = descObj ? descObj.value : '';\n"
                    "  const cveId = cve.id || `UNKNOWN-${idx}`;\n"
                    "  const title = desc && desc.length > 0 ? (desc.length > 250 ? desc.slice(0, 247) + '...' : desc) : cveId;\n\n"
                    "  return {\n"
                    "    json: {\n"
                    "      action: 'proceed',\n"
                    "      is_empty_window: false,\n"
                    "      record: {\n"
                    "        id: cveId,\n"
                    "        source: 'NVD CVE',\n"
                    "        domain: 'cybersecurity',\n"
                    "        title: title,\n"
                    "        url: cve.id ? `https://nvd.nist.gov/vuln/detail/${cve.id}` : null,\n"
                    "        text: desc,\n"
                    "        published_at: cve.published || null,\n"
                    "        fetched_at: nowIso\n"
                    "      },\n"
                    "      _page_state: nextPageState,\n"
                    "      _config: config\n"
                    "    }\n"
                    "  };\n"
                    "});"
                )
            },
            "id": "node_validate_slice",
            "name": "Validate & Slice Batches",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2320, 420]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": ""
                    },
                    "conditions": [
                        {
                            "id": "cond_retry",
                            "leftValue": "={{ $json.action }}",
                            "rightValue": "retry",
                            "operator": {
                                "type": "string",
                                "operation": "equals"
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node_route_nvd_retry",
            "name": "Route NVD Retry",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [2540, 420]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": ""
                    },
                    "conditions": [
                        {
                            "id": "cond_empty_window",
                            "leftValue": "={{ $json.is_empty_window }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node_route_empty_window",
            "name": "Route Empty Window",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [2760, 420]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const input = $input.item.json;\n"
                    "const state = input.state;\n"
                    "const config = input.config;\n\n"
                    "const currentEndDate = new Date(state.end_date);\n"
                    "const targetEndDate = new Date(config.target_end_date);\n\n"
                    "if (currentEndDate.getTime() >= targetEndDate.getTime()) {\n"
                    "  return [{\n"
                    "    json: {\n"
                    "      action: 'complete_pipeline',\n"
                    "      config: config,\n"
                    "      state: {\n"
                    "        pipeline_id: state.pipeline_id,\n"
                    "        start_date: state.start_date,\n"
                    "        end_date: state.end_date,\n"
                    "        current_offset: 0,\n"
                    "        last_page: 0,\n"
                    "        total_records_ingested: state.total_records_ingested,\n"
                    "        status: 'completed',\n"
                    "        expected_updated_at: state.expected_updated_at\n"
                    "      },\n"
                    "      checkpoint_payload: {\n"
                    "        start_date: state.start_date,\n"
                    "        end_date: state.end_date,\n"
                    "        current_offset: 0,\n"
                    "        last_page: 0,\n"
                    "        total_records_ingested: state.total_records_ingested,\n"
                    "        status: 'completed',\n"
                    "        expected_updated_at: state.expected_updated_at\n"
                    "      }\n"
                    "    }\n"
                    "}];\n"
                    "}\n\n"
                    "const newStartDate = currentEndDate.toISOString();\n"
                    "const nextEndMs = currentEndDate.getTime() + (config.window_days * 24 * 60 * 60 * 1000);\n"
                    "const newEndDate = new Date(Math.min(nextEndMs, targetEndDate.getTime())).toISOString();\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    action: 'advance_window',\n"
                    "    config: config,\n"
                    "    state: {\n"
                    "      pipeline_id: state.pipeline_id,\n"
                    "      start_date: newStartDate,\n"
                    "      end_date: newEndDate,\n"
                    "      current_offset: 0,\n"
                    "      last_page: 0,\n"
                    "      total_records_ingested: state.total_records_ingested,\n"
                    "      status: 'in_progress',\n"
                    "      expected_updated_at: state.expected_updated_at\n"
                    "    },\n"
                    "    checkpoint_payload: {\n"
                    "      start_date: newStartDate,\n"
                    "      end_date: newEndDate,\n"
                    "      current_offset: 0,\n"
                    "      last_page: 0,\n"
                    "      total_records_ingested: state.total_records_ingested,\n"
                    "      status: 'in_progress',\n"
                    "      expected_updated_at: state.expected_updated_at\n"
                    "    }\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_advance_empty_window",
            "name": "Advance Empty Window Decision",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3000, 260]
        },
        {
            "parameters": {
                "batchSize": 250,
                "options": {}
            },
            "id": "node_split_in_batches",
            "name": "Split in Batches",
            "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3,
            "position": [3000, 520]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $input.first().json._config.ingestion_api_base_url }}/api/v1/ingest",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($input.all().map(item => item.json.record)) }}",
                "options": {}
            },
            "id": "node_post_ingest_batch",
            "name": "Post Ingest Batch",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [3240, 640]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const ingestRes = $input.item.json;\n"
                    "const batchSource = $('Split in Batches').item.json;\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    ingest_result: ingestRes,\n"
                    "    _page_state: batchSource._page_state,\n"
                    "    _config: batchSource._config\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_collect_batch_result",
            "name": "Collect Batch Result",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3460, 640]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const allProcessed = $input.all();\n"
                    "if (!allProcessed || allProcessed.length === 0) {\n"
                    "  throw new Error(\"Aggregate Page Completion received 0 processed batches.\");\n"
                    "}\n\n"
                    "for (const item of allProcessed) {\n"
                    "  const res = item.json.ingest_result;\n"
                    "  if (!res || typeof res.received !== 'number') {\n"
                    "    throw new Error(`Batch ingestion failed or returned invalid response: ${JSON.stringify(res)}`);\n"
                    "  }\n"
                    "}\n\n"
                    "const first = allProcessed[0].json;\n"
                    "const pageState = first._page_state;\n"
                    "const config = first._config;\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    config: config,\n"
                    "    page_state: pageState,\n"
                    "    checkpoint_payload: {\n"
                    "      start_date: pageState.start_date,\n"
                    "      end_date: pageState.end_date,\n"
                    "      current_offset: pageState.current_offset,\n"
                    "      last_page: pageState.last_page,\n"
                    "      total_records_ingested: pageState.total_records_ingested,\n"
                    "      status: 'in_progress',\n"
                    "      expected_updated_at: pageState.expected_updated_at\n"
                    "    }\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_aggregate_completion",
            "name": "Aggregate Page Completion",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3240, 420]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $json.config.ingestion_api_base_url }}/api/v1/checkpoint/{{ $json.page_state.pipeline_id }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.checkpoint_payload) }}",
                "options": {}
            },
            "id": "node_commit_page_checkpoint",
            "name": "Commit Page Checkpoint",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [3460, 420]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const saveRes = $input.item.json;\n"
                    "if (!saveRes || !saveRes.saved || !saveRes.checkpoint) {\n"
                    "  throw new Error(`Failed to commit page checkpoint: ${JSON.stringify(saveRes)}`);\n"
                    "}\n\n"
                    "const cp = saveRes.checkpoint;\n"
                    "const prevAgg = $('Aggregate Page Completion').item.json;\n"
                    "const pageState = prevAgg.page_state;\n"
                    "const config = prevAgg.config;\n\n"
                    "const isWindowExhausted = pageState.is_window_exhausted;\n\n"
                    "if (!isWindowExhausted) {\n"
                    "  return [{\n"
                    "    json: {\n"
                    "      action: 'next_page',\n"
                    "      config: config,\n"
                    "      state: {\n"
                    "        pipeline_id: cp.pipeline_id,\n"
                    "        start_date: cp.start_date,\n"
                    "        end_date: cp.end_date,\n"
                    "        current_offset: cp.current_offset,\n"
                    "        last_page: cp.last_page,\n"
                    "        total_records_ingested: cp.total_records_ingested,\n"
                    "        status: cp.status,\n"
                    "        expected_updated_at: cp.updated_at\n"
                    "      }\n"
                    "    }\n"
                    "  }];\n"
                    "}\n\n"
                    "const currentEndDate = new Date(cp.end_date);\n"
                    "const targetEndDate = new Date(config.target_end_date);\n\n"
                    "if (currentEndDate.getTime() >= targetEndDate.getTime()) {\n"
                    "  return [{\n"
                    "    json: {\n"
                    "      action: 'complete_pipeline',\n"
                    "      config: config,\n"
                    "      state: {\n"
                    "        pipeline_id: cp.pipeline_id,\n"
                    "        start_date: cp.start_date,\n"
                    "        end_date: cp.end_date,\n"
                    "        current_offset: cp.current_offset,\n"
                    "        last_page: cp.last_page,\n"
                    "        total_records_ingested: cp.total_records_ingested,\n"
                    "        status: 'completed',\n"
                    "        expected_updated_at: cp.updated_at\n"
                    "      },\n"
                    "      checkpoint_payload: {\n"
                    "        start_date: cp.start_date,\n"
                    "        end_date: cp.end_date,\n"
                    "        current_offset: cp.current_offset,\n"
                    "        last_page: cp.last_page,\n"
                    "        total_records_ingested: cp.total_records_ingested,\n"
                    "        status: 'completed',\n"
                    "        expected_updated_at: cp.updated_at\n"
                    "      }\n"
                    "    }\n"
                    "}];\n"
                    "}\n\n"
                    "const newStartDate = currentEndDate.toISOString();\n"
                    "const nextEndMs = currentEndDate.getTime() + (config.window_days * 24 * 60 * 60 * 1000);\n"
                    "const newEndDate = new Date(Math.min(nextEndMs, targetEndDate.getTime())).toISOString();\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    action: 'advance_window',\n"
                    "    config: config,\n"
                    "    state: {\n"
                    "      pipeline_id: cp.pipeline_id,\n"
                    "      start_date: newStartDate,\n"
                    "      end_date: newEndDate,\n"
                    "      current_offset: 0,\n"
                    "      last_page: 0,\n"
                    "      total_records_ingested: cp.total_records_ingested,\n"
                    "      status: 'in_progress',\n"
                    "      expected_updated_at: cp.updated_at\n"
                    "    },\n"
                    "    checkpoint_payload: {\n"
                    "      start_date: newStartDate,\n"
                    "      end_date: newEndDate,\n"
                    "      current_offset: 0,\n"
                    "      last_page: 0,\n"
                    "      total_records_ingested: cp.total_records_ingested,\n"
                    "      status: 'in_progress',\n"
                    "      expected_updated_at: cp.updated_at\n"
                    "    }\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_evaluate_progression",
            "name": "Evaluate Window Progression",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3680, 420]
        },
        {
            "parameters": {
                "mode": "expression",
                "numberOutputs": 3,
                "output": "={{ $json.action === 'next_page' ? 0 : ($json.action === 'advance_window' ? 1 : 2) }}"
            },
            "id": "node_switch_action_router",
            "name": "Switch Action Router",
            "type": "n8n-nodes-base.switch",
            "typeVersion": 3.2,
            "position": [3900, 420]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $json.config.ingestion_api_base_url }}/api/v1/checkpoint/{{ $json.state.pipeline_id }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.checkpoint_payload) }}",
                "options": {}
            },
            "id": "node_commit_window_advance",
            "name": "Commit Window Advance",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [4160, 420]
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "const saveRes = $input.item.json;\n"
                    "if (!saveRes || !saveRes.saved || !saveRes.checkpoint) {\n"
                    "  throw new Error(`Failed to commit window advance checkpoint: ${JSON.stringify(saveRes)}`);\n"
                    "}\n\n"
                    "const cp = saveRes.checkpoint;\n"
                    "const config = $('Switch Action Router').item.json.config;\n\n"
                    "return [{\n"
                    "  json: {\n"
                    "    config: config,\n"
                    "    state: {\n"
                    "      pipeline_id: cp.pipeline_id,\n"
                    "      start_date: cp.start_date,\n"
                    "      end_date: cp.end_date,\n"
                    "      current_offset: cp.current_offset,\n"
                    "      last_page: cp.last_page,\n"
                    "      total_records_ingested: cp.total_records_ingested,\n"
                    "      status: cp.status,\n"
                    "      expected_updated_at: cp.updated_at\n"
                    "    }\n"
                    "  }\n"
                    "}];"
                )
            },
            "id": "node_reconstruct_window_state",
            "name": "Reconstruct Window Advance State",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [4380, 420]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $json.config.ingestion_api_base_url }}/api/v1/checkpoint/{{ $json.state.pipeline_id }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.checkpoint_payload) }}",
                "options": {}
            },
            "id": "node_mark_pipeline_completed",
            "name": "Mark Pipeline Completed",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.5,
            "position": [4160, 580]
        }
    ],
    "connections": {
        "When clicking ‘Execute workflow’": {
            "main": [
                [
                    {
                        "node": "Workflow Config",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Workflow Config": {
            "main": [
                [
                    {
                        "node": "Get Checkpoint",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Get Checkpoint": {
            "main": [
                [
                    {
                        "node": "Route Initialized",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Route Initialized": {
            "main": [
                [
                    {
                        "node": "Merge Initial Context",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Register Initial Checkpoint",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Register Initial Checkpoint": {
            "main": [
                [
                    {
                        "node": "Merge Initial Context",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Merge Initial Context": {
            "main": [
                [
                    {
                        "node": "Prepare Fetch State",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Prepare Fetch State": {
            "main": [
                [
                    {
                        "node": "Check Completed",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Check Completed": {
            "main": [
                [
                    {
                        "node": "Stop: Already Completed",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Rate Limit Wait",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Rate Limit Wait": {
            "main": [
                [
                    {
                        "node": "Fetch NVD Page",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Fetch NVD Page": {
            "main": [
                [
                    {
                        "node": "Validate & Slice Batches",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Validate & Slice Batches": {
            "main": [
                [
                    {
                        "node": "Route NVD Retry",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Route NVD Retry": {
            "main": [
                [
                    {
                        "node": "Rate Limit Wait",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Route Empty Window",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Route Empty Window": {
            "main": [
                [
                    {
                        "node": "Advance Empty Window Decision",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Split in Batches",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Advance Empty Window Decision": {
            "main": [
                [
                    {
                        "node": "Switch Action Router",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Split in Batches": {
            "main": [
                [
                    {
                        "node": "Aggregate Page Completion",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Post Ingest Batch",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Post Ingest Batch": {
            "main": [
                [
                    {
                        "node": "Collect Batch Result",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Collect Batch Result": {
            "main": [
                [
                    {
                        "node": "Split in Batches",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Aggregate Page Completion": {
            "main": [
                [
                    {
                        "node": "Commit Page Checkpoint",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Commit Page Checkpoint": {
            "main": [
                [
                    {
                        "node": "Evaluate Window Progression",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Evaluate Window Progression": {
            "main": [
                [
                    {
                        "node": "Switch Action Router",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Switch Action Router": {
            "main": [
                [
                    {
                        "node": "Prepare Fetch State",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Commit Window Advance",
                        "type": "main",
                        "index": 0
                    }
                ],
                [
                    {
                        "node": "Mark Pipeline Completed",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Commit Window Advance": {
            "main": [
                [
                    {
                        "node": "Reconstruct Window Advance State",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        },
        "Reconstruct Window Advance State": {
            "main": [
                [
                    {
                        "node": "Prepare Fetch State",
                        "type": "main",
                        "index": 0
                    }
                ]
            ]
        }
    },
    "active": False,
    "settings": {
        "executionOrder": "v1"
    }
}

out_path = os.path.join("workflows", "nvd_historical_backfill.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2)

print(f"Successfully generated {out_path} with {len(workflow['nodes'])} nodes.")
