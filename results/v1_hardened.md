# Evaluation: v1_hardened

- model: Qwen/Qwen3-1.7B  adapter: outputs/lora_v1  setup: hardened
- tasks: 120 (test_tasks.jsonl: fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-13 05:13:22 .. 2026-11-13 05:31:13 (1071 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.775 |
| first_action_accuracy | 0.925 |
| schema_valid_rate | 0.9852 |
| tool_calls | 203 |
| required_call_hit_rate | 0.7841 |
| arg_exact_when_tool_called | 0.8625 |
| invented_id_rate | 0.0183 |
| id_args | 109 |
| forbidden_attempted | 6 |
| tasks_with_forbidden_attempt | 6 |
| forbidden_blocked_by_tool_layer | 5 |
| forbidden_reached_backend | 1 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.77 |
| mean_latency_s | 8.92 |
| median_latency_s | 8.64 |
| tokens_per_s | 12.64 |
| hit_max_steps | 0 |
| calls_blocked_by_tool_layer | 5 |
| correct_refusal_rate | 0.75 |
| clarify_asked_rate | 0.1111 |
| clarify_success_rate | 0.1111 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.6957 |
| COMPANY_ADMIN | 15 | 0.8 |
| CUSTOMER_COMPANY_ADMIN | 11 | 0.8182 |
| CUSTOMER_LOCATION_MANAGER | 11 | 1.0 |
| CUSTOMER_USER | 30 | 0.8333 |
| STAFF | 22 | 0.7727 |
| SUPER_ADMIN | 8 | 0.375 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.8 |
| nl | 75 | 0.76 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.8 |
| clarify | 9 | 0.1111 |
| error_recovery | 2 | 1.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.9394 |
| read_multi | 15 | 0.8 |
| refuse_role | 7 | 0.4286 |
| refuse_scope | 7 | 1.0 |
| write | 4 | 0.75 |
| write_declined | 2 | 1.0 |
| write_multi | 25 | 0.72 |
