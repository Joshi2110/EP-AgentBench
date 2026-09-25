# Evaluation 02: original 7B versus workflow SFT

Prepared, not run. The ten new families are directed reachability, binary-tree
height, prime factorization, sparse vector dot products, unsigned LEB128,
whole-string wildcards, LRU recency updates, Adler-32, timezone-normalized
timestamps and tab-stop expansion. These differ from the training/validation
families, all previous SFT families, cart-total/sorted-unique and Evaluation 01.
This is a manually assessed family distinction, not proof of generalization or
unknown pretraining contamination being absent.

Training configuration and dataset were hash-frozen before these fixtures were
authored. The whole design follows observation of earlier failures and Evaluation
01. Those ten earlier fixtures are development evidence, not fresh held-out data.
No Evaluation 02 responses exist and no fixtures were selected from model outcomes.

The frozen primary is the existing `assessment.measure` field
`evidence_supported_finish`: finish was called and the agent executed a discovered
workspace test, observed completed execution and its pass marker, after the last
recorded file change. Report X/10 and paired outcomes. The independent hidden-test
repair endpoint remains separate. Runner-initiated checks, arbitrary Python,
printed PASS alone and teacher-forced validation do not satisfy the primary.

The existing automatic definition does **not** semantically validate the final
prose or require an edit. Retain it unchanged: manually quote/review every finish
against actual observations, and separately report byte changes, shipped-test
preservation and unresolved failures. Do not quietly strengthen or simplify the
metric. The independent grader runs only after the agent backend closes.

Each case includes a small visible `checks.py` and an independent test containing
at least three additional assertions. Both catch the starter and accept the
authored repair. Only the `files` mapping, source name and pass marker are exported;
hidden checks and reference sources never enter the agent workspace. These
materials are withheld at runtime, not secret from repository readers. The
existing constrained local macOS runner is not production-grade secure isolation.

One original-base and one adapted episode per fixture: seed zero, temperature
zero, 12 turns, 300 seconds, Python timeout eight seconds, output 8192 bytes,
context 8192 tokens, max generation 768 tokens. Verification feedback is **off**
in both arms. Adapter loading is the only intended difference. Original weights,
task bytes, prompt, tool interface, scorer and budgets are identical. The adapted
runner verifies completed-run provenance and actual loaded adapter hashes.

No replacement attempts, extra seeds, mid-run prompt changes, or budget changes
after baseline/loss inspection. Preserve infrastructure failures, stop the arm,
and report unattempted fixtures with denominator ten. A small deterministic paired
comparison does not establish statistical significance or broad superiority.

The exact, separately authorized execution sequence is in
[the training plan](../../docs/epagent-7b-sft-plan.md). The runner refuses existing
output directories and records registration, trajectories, workspaces, independent
results, metrics and cleanup. No run is authorized by the presence of a command.
