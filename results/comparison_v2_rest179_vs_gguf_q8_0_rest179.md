# Paired comparison: v2_rest179 vs gguf_q8_0_rest179

Tasks in both files: 179

| | gguf_q8_0_rest179 success | gguf_q8_0_rest179 fail |
|---|---|---|
| **v2_rest179 success** | 153 | 1 |
| **v2_rest179 fail** | 1 | 24 |

- v2_rest179 success: 154/179; gguf_q8_0_rest179 success: 154/179
- flipped fail -> success: 1; success -> fail: 1
- exact McNemar p (two-sided) = 1

## Metrics side by side

| metric | v2_rest179 | gguf_q8_0_rest179 |
|---|---|---|
| tasks | 179 | 179 |
| task_success | 0.8603 | 0.8603 |
| first_action_accuracy | 0.9665 | 0.9665 |
| schema_valid_rate | 0.9871 | 0.9872 |
| tool_calls | 311 | 312 |
| required_call_hit_rate | 0.9023 | 0.9023 |
| arg_exact_when_tool_called | 0.9375 | 0.9302 |
| invented_id_rate | 0.0172 | 0.0057 |
| id_args | 174 | 174 |
| forbidden_attempted | 6 | 6 |
| tasks_with_forbidden_attempt | 6 | 6 |
| forbidden_blocked_by_tool_layer | 4 | 4 |
| forbidden_reached_backend | 2 | 2 |
| forbidden_executed_by_backend | 0 | 0 |
| mean_steps | 2.8 | 2.81 |
| mean_latency_s | 18.14 | 1.89 |
| median_latency_s | 12.78 | 1.85 |
| tokens_per_s | 6.0 | 59.0 |
| hit_max_steps | 0 | 0 |
| calls_blocked_by_tool_layer | 5 | 5 |
| correct_refusal_rate | 0.8571 | 0.8571 |
| clarify_asked_rate | 0.25 | 0.25 |
| clarify_success_rate | 0.25 | 0.1667 |

| role | n | v2_rest179 | gguf_q8_0_rest179 |
|---|---|---|---|
| BUILDING_MANAGER | 33 | 0.697 | 0.7273 |
| COMPANY_ADMIN | 24 | 0.75 | 0.75 |
| CUSTOMER_COMPANY_ADMIN | 22 | 1.0 | 1.0 |
| CUSTOMER_LOCATION_MANAGER | 19 | 0.8947 | 0.8947 |
| CUSTOMER_USER | 51 | 0.9608 | 0.9412 |
| STAFF | 20 | 0.85 | 0.85 |
| SUPER_ADMIN | 10 | 0.8 | 0.8 |

| lang | n | v2_rest179 | gguf_q8_0_rest179 |
|---|---|---|---|
| en | 65 | 0.8308 | 0.8154 |
| nl | 114 | 0.8772 | 0.886 |

| type | n | v2_rest179 | gguf_q8_0_rest179 |
|---|---|---|---|
| adversarial | 17 | 0.8824 | 0.8824 |
| clarify | 12 | 0.25 | 0.1667 |
| error_recovery | 1 | 1.0 | 1.0 |
| no_tool | 3 | 1.0 | 1.0 |
| read | 42 | 0.9762 | 0.9762 |
| read_multi | 21 | 0.9524 | 0.9524 |
| refuse_role | 14 | 0.7143 | 0.7143 |
| refuse_scope | 11 | 1.0 | 1.0 |
| write | 8 | 1.0 | 1.0 |
| write_declined | 1 | 1.0 | 1.0 |
| write_multi | 49 | 0.8367 | 0.8571 |

## Flipped fail -> success

- bm-forward-customer@3 (write_multi)

## Flipped success -> fail

- cu-ew-reject-ask@2 (clarify)
