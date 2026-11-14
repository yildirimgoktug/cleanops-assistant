# Evaluation: gguf_q4_k_m

- model: Qwen/Qwen3-1.7B  adapter: None  setup: hardened
- tasks: 120 (test_tasks.jsonl: fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-14 15:00:10 .. 2026-11-14 15:03:13 (183 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.725 |
| first_action_accuracy | 0.9083 |
| schema_valid_rate | 0.9809 |
| tool_calls | 209 |
| required_call_hit_rate | 0.7955 |
| arg_exact_when_tool_called | 0.9091 |
| invented_id_rate | 0.0603 |
| id_args | 116 |
| forbidden_attempted | 7 |
| tasks_with_forbidden_attempt | 7 |
| forbidden_blocked_by_tool_layer | 4 |
| forbidden_reached_backend | 3 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.82 |
| mean_latency_s | 1.52 |
| median_latency_s | 1.38 |
| tokens_per_s | 74.57 |
| hit_max_steps | 0 |
| calls_blocked_by_tool_layer | 6 |
| correct_refusal_rate | 0.75 |
| clarify_asked_rate | 0.1111 |
| clarify_success_rate | 0.1111 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.6087 |
| COMPANY_ADMIN | 15 | 0.6 |
| CUSTOMER_COMPANY_ADMIN | 11 | 0.9091 |
| CUSTOMER_LOCATION_MANAGER | 11 | 0.9091 |
| CUSTOMER_USER | 30 | 0.7667 |
| STAFF | 22 | 0.6818 |
| SUPER_ADMIN | 8 | 0.75 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.8222 |
| nl | 75 | 0.6667 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.7 |
| clarify | 9 | 0.1111 |
| error_recovery | 2 | 1.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.7576 |
| read_multi | 15 | 0.9333 |
| refuse_role | 7 | 0.5714 |
| refuse_scope | 7 | 1.0 |
| write | 4 | 0.5 |
| write_declined | 2 | 1.0 |
| write_multi | 25 | 0.68 |
