# Evaluation: gguf_f16

- model: Qwen/Qwen3-1.7B  adapter: None  setup: hardened
- tasks: 120 (test_tasks.jsonl: fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-14 15:13:36 .. 2026-11-14 15:19:23 (347 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.8917 |
| first_action_accuracy | 0.9417 |
| schema_valid_rate | 0.9851 |
| tool_calls | 201 |
| required_call_hit_rate | 0.9205 |
| arg_exact_when_tool_called | 0.9419 |
| invented_id_rate | 0.0 |
| id_args | 109 |
| forbidden_attempted | 2 |
| tasks_with_forbidden_attempt | 2 |
| forbidden_blocked_by_tool_layer | 2 |
| forbidden_reached_backend | 0 |
| forbidden_executed_by_backend | 0 |
| mean_steps | 2.75 |
| mean_latency_s | 2.88 |
| median_latency_s | 2.65 |
| tokens_per_s | 39.7 |
| hit_max_steps | 0 |
| calls_blocked_by_tool_layer | 4 |
| correct_refusal_rate | 0.9167 |
| clarify_asked_rate | 0.3333 |
| clarify_success_rate | 0.3333 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.8696 |
| COMPANY_ADMIN | 15 | 0.8667 |
| CUSTOMER_COMPANY_ADMIN | 11 | 1.0 |
| CUSTOMER_LOCATION_MANAGER | 11 | 1.0 |
| CUSTOMER_USER | 30 | 0.9 |
| STAFF | 22 | 0.8182 |
| SUPER_ADMIN | 8 | 0.875 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.9556 |
| nl | 75 | 0.8533 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.9 |
| clarify | 9 | 0.3333 |
| error_recovery | 2 | 1.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.9394 |
| read_multi | 15 | 1.0 |
| refuse_role | 7 | 0.8571 |
| refuse_scope | 7 | 1.0 |
| write | 4 | 1.0 |
| write_declined | 2 | 1.0 |
| write_multi | 25 | 0.88 |
