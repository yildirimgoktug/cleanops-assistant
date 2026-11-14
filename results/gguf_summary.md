| set | HF bf16 + adapter (published) | Q4_K_M | Q5_K_M | Q8_0 | F16 |
|---|---|---|---|---|---|
| 120-task subset | 0.900 | 0.725 | 0.825 | 0.875 | 0.892 |
| other 179 tasks | 0.860 | not run | not run | 0.860 | not run |
| injection set (99) | 0.859 | 0.808 | 0.788 | 0.869 | 0.869 |

| variant | tokens/s (server decode) | tokens/s (harness, incl. prefill) | TTFT median / mean / p90 (s) | mean latency per task (s) |
|---|---|---|---|---|
| HF bf16 + adapter (published) | - | 9.9 | - | 11.57 |
| Q4_K_M | 101.84 | 74.57 | 0.047 / 0.153 / 0.55 | 1.52 |
| Q5_K_M | 94.72 | 71.29 | 0.047 / 0.156 / 0.553 | 1.63 |
| Q8_0 | 72.9 | 57.95 | 0.044 / 0.163 / 0.551 | 2.0 |
| F16 | 45.43 | 39.7 | 0.05 / 0.157 / 0.542 | 2.88 |
