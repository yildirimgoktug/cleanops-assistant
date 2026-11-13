# Evaluation: v2_rest179

- model: Qwen/Qwen3-1.7B  adapter: outputs/lora_v2  setup: hardened
- tasks: 179 (test_tasks.jsonl: all tasks NOT in the fixed subset of 120 (subset_120_ids.json))
- run: 2026-11-13 17:38:08 .. 2026-11-13 18:32:18 (3250 s)

| metric | value |
|---|---|
| tasks | 179 |
| task_success | 0.8603 |
| first_action_accuracy | 0.9665 |
| schema_valid_rate | 0.9871 |
| tool_calls | 311 |
| required_call_hit_rate | 0.9023 |
| arg_exact_when_tool_called | 0.9375 |
| invented_id_rate | 0.0172 |
| id_args | 174 |
| forbidden_attempted | 6 |
| tasks_with_forbidden_attempt | 6 |
| forbidden_blocked_by_tool_layer | 4 |
| forbidden_reached_backend | 2 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.8 |
| mean_latency_s | 18.14 |
| median_latency_s | 12.78 |
| tokens_per_s | 6.0 |
| hit_max_steps | 0 |
| calls_blocked_by_tool_layer | 5 |
| correct_refusal_rate | 0.8571 |
| clarify_asked_rate | 0.25 |
| clarify_success_rate | 0.25 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 33 | 0.697 |
| COMPANY_ADMIN | 24 | 0.75 |
| CUSTOMER_COMPANY_ADMIN | 22 | 1.0 |
| CUSTOMER_LOCATION_MANAGER | 19 | 0.8947 |
| CUSTOMER_USER | 51 | 0.9608 |
| STAFF | 20 | 0.85 |
| SUPER_ADMIN | 10 | 0.8 |

| lang | n | success |
|---|---|---|
| en | 65 | 0.8308 |
| nl | 114 | 0.8772 |

| type | n | success |
|---|---|---|
| adversarial | 17 | 0.8824 |
| clarify | 12 | 0.25 |
| error_recovery | 1 | 1.0 |
| no_tool | 3 | 1.0 |
| read | 42 | 0.9762 |
| read_multi | 21 | 0.9524 |
| refuse_role | 14 | 0.7143 |
| refuse_scope | 11 | 1.0 |
| write | 8 | 1.0 |
| write_declined | 1 | 1.0 |
| write_multi | 49 | 0.8367 |
