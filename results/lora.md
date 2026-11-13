# Evaluation: lora

- model: Qwen/Qwen3-1.7B  adapter: outputs/lora_v1
- tasks: 120 (fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-13 03:48:53 .. 2026-11-13 04:11:21 (1347 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.8083 |
| first_action_accuracy | 0.925 |
| schema_valid_rate | 1.0 |
| tool_calls | 211 |
| required_call_hit_rate | 0.8523 |
| arg_exact_when_tool_called | 0.9259 |
| invented_id_rate | 0.0085 |
| id_args | 118 |
| forbidden_attempted | 6 |
| tasks_with_forbidden_attempt | 6 |
| forbidden_reached_backend | 6 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.83 |
| mean_latency_s | 11.22 |
| median_latency_s | 9.36 |
| tokens_per_s | 10.03 |
| hit_max_steps | 0 |
| correct_refusal_rate | 0.75 |
| clarify_asked_rate | 0.2222 |
| clarify_success_rate | 0.2222 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.8696 |
| COMPANY_ADMIN | 15 | 0.8 |
| CUSTOMER_COMPANY_ADMIN | 11 | 0.8182 |
| CUSTOMER_LOCATION_MANAGER | 11 | 1.0 |
| CUSTOMER_USER | 30 | 0.9 |
| STAFF | 22 | 0.6364 |
| SUPER_ADMIN | 8 | 0.5 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.8667 |
| nl | 75 | 0.7733 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.7 |
| clarify | 9 | 0.2222 |
| error_recovery | 2 | 1.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.9091 |
| read_multi | 15 | 0.8667 |
| refuse_role | 7 | 0.5714 |
| refuse_scope | 7 | 1.0 |
| write | 4 | 1.0 |
| write_declined | 2 | 1.0 |
| write_multi | 25 | 0.8 |
