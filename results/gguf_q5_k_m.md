# Evaluation: gguf_q5_k_m

- model: Qwen/Qwen3-1.7B  adapter: None  setup: hardened
- tasks: 120 (test_tasks.jsonl: fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-14 15:06:36 .. 2026-11-14 15:09:53 (197 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.825 |
| first_action_accuracy | 0.9333 |
| schema_valid_rate | 0.9899 |
| tool_calls | 199 |
| required_call_hit_rate | 0.8864 |
| arg_exact_when_tool_called | 0.9286 |
| invented_id_rate | 0.0364 |
| id_args | 110 |
| forbidden_attempted | 3 |
| tasks_with_forbidden_attempt | 3 |
| forbidden_blocked_by_tool_layer | 2 |
| forbidden_reached_backend | 1 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.73 |
| mean_latency_s | 1.63 |
| median_latency_s | 1.53 |
| tokens_per_s | 71.29 |
| hit_max_steps | 0 |
| calls_blocked_by_tool_layer | 3 |
| correct_refusal_rate | 0.875 |
| clarify_asked_rate | 0.1111 |
| clarify_success_rate | 0.1111 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.7391 |
| COMPANY_ADMIN | 15 | 0.8 |
| CUSTOMER_COMPANY_ADMIN | 11 | 0.9091 |
| CUSTOMER_LOCATION_MANAGER | 11 | 0.9091 |
| CUSTOMER_USER | 30 | 0.9 |
| STAFF | 22 | 0.7273 |
| SUPER_ADMIN | 8 | 0.875 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.9333 |
| nl | 75 | 0.76 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.9 |
| clarify | 9 | 0.1111 |
| error_recovery | 2 | 1.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.9394 |
| read_multi | 15 | 0.8667 |
| refuse_role | 7 | 0.7143 |
| refuse_scope | 7 | 1.0 |
| write | 4 | 1.0 |
| write_declined | 2 | 1.0 |
| write_multi | 25 | 0.76 |
