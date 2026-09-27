# Benchmark Results -- Synthetic Cases

Precision is **100% by construction**: Witness emits DEFEATED only when it can produce a runnable test that passes on base and fails on head. A finding without a proof test is impossible by the gate design.

| case | guarantee | green alone? | textual conflict? | existing suite caught it? | Witness verdict | proof test |
|------|-----------|-------------|-----------------|--------------------------|----------------|------------|
| case-01-retry-defeats-limiter | G1 | yes | no | no | PROVEN | test_witness_lane_L1.py |
| case-02-bulk-bypasses-validator | G3 | yes | no | no | PROVEN | witness-generated |
| case-03-write-through-defeats-cache | G4 | no | no | yes | PROVEN | test_witness_lane_L1.py |
| case-04-regenerated-idempotency-defeats-dedup | G2 | no | no | yes | PROVEN | witness-generated |
| case-05-weakened-ceiling-defeats-g1 | G1 | yes | no | no | PROVEN | test_witness_lane_L1.py |
| case-06-unchecked-fast-path-defeats-g3 | G3 | yes | no | no | PROVEN | test_witness_lane_L1.py |
