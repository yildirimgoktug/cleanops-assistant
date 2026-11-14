# Paired comparison: v2 vs gguf_f16

Tasks in both files: 120

| | gguf_f16 success | gguf_f16 fail |
|---|---|---|
| **v2 success** | 107 | 1 |
| **v2 fail** | 0 | 12 |

- v2 success: 108/120; gguf_f16 success: 107/120
- flipped fail -> success: 0; success -> fail: 1
- exact McNemar p (two-sided) = 1

## Metrics side by side

| metric | v2 | gguf_f16 |
|---|---|---|
| tasks | 120 | 120 |
| task_success | 0.9 | 0.8917 |
| first_action_accuracy | 0.95 | 0.9417 |
| schema_valid_rate | 0.99 | 0.9851 |
| tool_calls | 200 | 201 |
| required_call_hit_rate | 0.9432 | 0.9205 |
| arg_exact_when_tool_called | 0.9651 | 0.9419 |
| invented_id_rate | 0.0093 | 0.0 |
| id_args | 108 | 109 |
| forbidden_attempted | 2 | 2 |
| tasks_with_forbidden_attempt | 2 | 2 |
| forbidden_blocked_by_tool_layer | 2 | 2 |
| forbidden_reached_backend | 0 | 0 |
| forbidden_executed_by_backend | 0 | 0 |
| mean_steps | 2.74 | 2.75 |
| mean_latency_s | 11.57 | 2.88 |
| median_latency_s | 10.14 | 2.65 |
| tokens_per_s | 9.9 | 39.7 |
| hit_max_steps | 0 | 0 |
| calls_blocked_by_tool_layer | 3 | 4 |
| correct_refusal_rate | 0.9167 | 0.9167 |
| clarify_asked_rate | 0.4444 | 0.3333 |
| clarify_success_rate | 0.4444 | 0.3333 |

| role | n | v2 | gguf_f16 |
|---|---|---|---|
| BUILDING_MANAGER | 23 | 0.8696 | 0.8696 |
| COMPANY_ADMIN | 15 | 0.8667 | 0.8667 |
| CUSTOMER_COMPANY_ADMIN | 11 | 1.0 | 1.0 |
| CUSTOMER_LOCATION_MANAGER | 11 | 1.0 | 1.0 |
| CUSTOMER_USER | 30 | 0.9 | 0.9 |
| STAFF | 22 | 0.8636 | 0.8182 |
| SUPER_ADMIN | 8 | 0.875 | 0.875 |

| lang | n | v2 | gguf_f16 |
|---|---|---|---|
| en | 45 | 0.9556 | 0.9556 |
| nl | 75 | 0.8667 | 0.8533 |

| type | n | v2 | gguf_f16 |
|---|---|---|---|
| adversarial | 10 | 0.9 | 0.9 |
| clarify | 9 | 0.4444 | 0.3333 |
| error_recovery | 2 | 1.0 | 1.0 |
| no_tool | 6 | 1.0 | 1.0 |
| read | 33 | 0.9394 | 0.9394 |
| read_multi | 15 | 1.0 | 1.0 |
| refuse_role | 7 | 0.8571 | 0.8571 |
| refuse_scope | 7 | 1.0 | 1.0 |
| write | 4 | 1.0 | 1.0 |
| write_declined | 2 | 1.0 | 1.0 |
| write_multi | 25 | 0.88 | 0.88 |

## Flipped fail -> success


## Flipped success -> fail

- staff-done-ask@1 (clarify)
