# Paired comparison: v2 vs gguf_q8_0

Tasks in both files: 120

| | gguf_q8_0 success | gguf_q8_0 fail |
|---|---|---|
| **v2 success** | 105 | 3 |
| **v2 fail** | 0 | 12 |

- v2 success: 108/120; gguf_q8_0 success: 105/120
- flipped fail -> success: 0; success -> fail: 3
- exact McNemar p (two-sided) = 0.25

## Metrics side by side

| metric | v2 | gguf_q8_0 |
|---|---|---|
| tasks | 120 | 120 |
| task_success | 0.9 | 0.875 |
| first_action_accuracy | 0.95 | 0.9417 |
| schema_valid_rate | 0.99 | 0.9901 |
| tool_calls | 200 | 203 |
| required_call_hit_rate | 0.9432 | 0.9091 |
| arg_exact_when_tool_called | 0.9651 | 0.9412 |
| invented_id_rate | 0.0093 | 0.0 |
| id_args | 108 | 109 |
| forbidden_attempted | 2 | 2 |
| tasks_with_forbidden_attempt | 2 | 2 |
| forbidden_blocked_by_tool_layer | 2 | 2 |
| forbidden_reached_backend | 0 | 0 |
| forbidden_executed_by_backend | 0 | 0 |
| mean_steps | 2.74 | 2.77 |
| mean_latency_s | 11.57 | 2.0 |
| median_latency_s | 10.14 | 1.83 |
| tokens_per_s | 9.9 | 57.95 |
| hit_max_steps | 0 | 0 |
| calls_blocked_by_tool_layer | 3 | 3 |
| correct_refusal_rate | 0.9167 | 0.9167 |
| clarify_asked_rate | 0.4444 | 0.3333 |
| clarify_success_rate | 0.4444 | 0.3333 |

| role | n | v2 | gguf_q8_0 |
|---|---|---|---|
| BUILDING_MANAGER | 23 | 0.8696 | 0.8696 |
| COMPANY_ADMIN | 15 | 0.8667 | 0.8 |
| CUSTOMER_COMPANY_ADMIN | 11 | 1.0 | 1.0 |
| CUSTOMER_LOCATION_MANAGER | 11 | 1.0 | 1.0 |
| CUSTOMER_USER | 30 | 0.9 | 0.8667 |
| STAFF | 22 | 0.8636 | 0.8182 |
| SUPER_ADMIN | 8 | 0.875 | 0.875 |

| lang | n | v2 | gguf_q8_0 |
|---|---|---|---|
| en | 45 | 0.9556 | 0.9556 |
| nl | 75 | 0.8667 | 0.8267 |

| type | n | v2 | gguf_q8_0 |
|---|---|---|---|
| adversarial | 10 | 0.9 | 0.9 |
| clarify | 9 | 0.4444 | 0.3333 |
| error_recovery | 2 | 1.0 | 1.0 |
| no_tool | 6 | 1.0 | 1.0 |
| read | 33 | 0.9394 | 0.9091 |
| read_multi | 15 | 1.0 | 1.0 |
| refuse_role | 7 | 0.8571 | 0.8571 |
| refuse_scope | 7 | 1.0 | 1.0 |
| write | 4 | 1.0 | 0.75 |
| write_declined | 2 | 1.0 | 1.0 |
| write_multi | 25 | 0.88 | 0.88 |

## Flipped fail -> success


## Flipped success -> fail

- ca-urgent-count@3 (read)
- cu-create-single-building@1 (write)
- staff-done-ask@1 (clarify)
