# Evaluation: baseline

- model: Qwen/Qwen3-1.7B  adapter: None
- tasks: 120 (fixed seeded subset of 120 (ids in subset_120_ids.json))
- run: 2026-11-13 00:52:53 .. 2026-11-13 01:25:42 (1969 s)

| metric | value |
|---|---|
| tasks | 120 |
| task_success | 0.2833 |
| first_action_accuracy | 0.6083 |
| schema_valid_rate | 0.9273 |
| tool_calls | 220 |
| required_call_hit_rate | 0.2727 |
| arg_exact_when_tool_called | 0.4898 |
| invented_id_rate | 0.3911 |
| id_args | 179 |
| forbidden_attempted | 15 |
| tasks_with_forbidden_attempt | 12 |
| forbidden_reached_backend | 15 |
| forbidden_executed_by_backend | 3 |
| mean_steps | 2.81 |
| mean_latency_s | 16.4 |
| median_latency_s | 9.43 |
| tokens_per_s | 7.78 |
| hit_max_steps | 11 |
| correct_refusal_rate | 0.5417 |
| clarify_asked_rate | 0.6667 |
| clarify_success_rate | 0.0 |

| role | n | success |
|---|---|---|
| BUILDING_MANAGER | 23 | 0.2174 |
| COMPANY_ADMIN | 15 | 0.4 |
| CUSTOMER_COMPANY_ADMIN | 11 | 0.1818 |
| CUSTOMER_LOCATION_MANAGER | 11 | 0.4545 |
| CUSTOMER_USER | 30 | 0.3333 |
| STAFF | 22 | 0.1818 |
| SUPER_ADMIN | 8 | 0.25 |

| lang | n | success |
|---|---|---|
| en | 45 | 0.1778 |
| nl | 75 | 0.3467 |

| type | n | success |
|---|---|---|
| adversarial | 10 | 0.6 |
| clarify | 9 | 0.0 |
| error_recovery | 2 | 0.0 |
| no_tool | 6 | 1.0 |
| read | 33 | 0.3636 |
| read_multi | 15 | 0.1333 |
| refuse_role | 7 | 0.1429 |
| refuse_scope | 7 | 0.8571 |
| write | 4 | 0.25 |
| write_declined | 2 | 0.0 |
| write_multi | 25 | 0.0 |
