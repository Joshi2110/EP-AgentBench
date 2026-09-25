# Training feasibility: what this machine can and cannot support

A plan, not an implementation. No training, inference or RL was run to write it.
Every memory and timing figure below is either measured on this machine or
derived from a measurement, and the source is named.

## Measurements this rests on

| Fact | Value | Source |
| --- | --- | --- |
| 1.5B 4-bit LoRA training, 40 updates, seq 2048, batch 1, grad checkpoint | 2.85 GB peak MLX, 1.69 GB RSS, 247 s | `artifacts/ep-agent/sft-v2/.../tool-use-lora-v2/run.json` |
| 1.5B weights on disk | 0.82 GB | model manifest |
| 7B weights on disk | 4.00 GB | model manifest |
| 7B inference peak | 4.76 to 4.92 GB MLX, 1.35 to 1.61 GB RSS | Evaluation 01, 20 episodes |
| 7B episode wall time | 46 to 293 s | Evaluation 01 |
| 7B dimensions | hidden 3584, 28 layers, vocab 152064, 28 heads, 4 KV | `config.json` |
| Rank-8 Q/V LoRA, last 4 layers, 7B | 360,448 trainable parameters | computed |
| float32 logits at seq 2048 / 1024 | 1.16 / 0.58 GB | computed, vocab-dominated |
| mlx-lm 0.31.3 RL support | **none**: no PPO, GRPO, DPO or reward module | module listing |
| Machine | 16 GB unified, ~6.8 GB reclaimable, swap 9.5 of 10.2 GB used | measured |

## A. 7B 4-bit LoRA SFT: feasible with conditions

Estimate by decomposition. The 1.5B run peaked at 2.85 GB against 0.82 GB of
weights, so roughly 2.0 GB of non-weight overhead at seq 2048. Of that, logits
are about 1.16 GB and do not grow with model size, because the vocabulary is the
same. Checkpointed activations scale with hidden size: 28 layers by 2048 by 3584
by 4 bytes is about 0.82 GB for the 7B against 0.35 GB for the 1.5B. Optimizer
state is negligible at 360,448 parameters.

That gives roughly **4.0 + 2.5 = 6.5 GB peak MLX at seq 2048**, and about
**5.5 GB at seq 1024**. Against 16 GB total with ~6.8 GB currently reclaimable
and the worker's existing 7 GiB MLX cap, seq 2048 is marginal and seq 1024 has
real headroom.

Verdict: feasible at **batch 1, seq ≤1024, gradient checkpointing on, rank 8,
Q/V on at most the last 4 layers**. Measure first with a load-and-attach check
that performs zero optimizer steps, exactly as was done for the 1.5B, and abort
if the measured peak exceeds 6 GB.

Compute: the 1.5B ran 6.2 s per update. The 7B is about 4.9 times the weights,
so **15 to 30 s per update** at seq 1024; 150 updates is roughly 40 to 75
minutes. Effort: the SFT pipeline exists but hard-pins the 1.5B in
`sft.local_model`; extending it to the existing two-model allowlist is a small
contained change.

## B. Online RL with 7B rollouts: not realistically feasible

Three independent reasons, any one of which would be limiting.

**No library support.** mlx-lm 0.31.3 ships LoRA SFT and nothing else. Rollout
collection, advantage estimation, a policy-gradient loss and KL control would
all be written from scratch, against an API with no RL surface to build on.

**Memory.** PPO needs a reference policy alongside the trainee. Two 7B copies is
8 GB of weights before activations. Toggling the LoRA adapter off to recompute
reference log-probabilities avoids a second copy and is the one real mitigation,
but it doubles forward passes on an already marginal budget.

**Throughput against reward sparsity.** An episode costs 46 to 293 seconds,
measured. At roughly two minutes each, a thousand episodes is 33 hours of pure
rollout on one machine with no batching. The reward is sparse: the baseline
solves 3 of 10, so most episodes would carry no gradient signal at all.

Verdict: do not attempt on this machine.

## C. Small student, 7B as teacher: feasible but weak as stated

The 1.5B LoRA path is measured and works. The problem is the teacher. The 7B
reaches 3/10 functional repair and 0/10 evidence-supported workflows, and two
prior SFT rounds on the 1.5B each produced 0/4. Distilling a weak teacher into a
smaller student is unlikely to produce a measurable gain.

A filtered variant is defensible: use the 7B purely as a generator, keep only
trajectories that pass the hidden tests, and train on those. At 3/10 success that
needs many episodes to accumulate usable data, and the resulting set would be
biased toward the fixtures the teacher already solves.

## D. Verifiable intermediate rewards without leaking the evaluation

The rule: reward is computed only from observable workspace state and recorded
actions, never from a hidden test, and tool compliance is never folded into
functional repair.

Signals already available and already measured per episode: schema-valid call
fraction, an accepted edit that changes bytes, final source parsing, an
agent-initiated execution of the **workspace-provided** test, that test's
observed outcome, and a finish that follows such a run after the last change.

Two cautions from the measured data. Schema compliance is already at ceiling in
the baseline, 0 rejections in 10 episodes, so it offers no headroom. And the
visible test is a **proxy** for repair, not repair: Evaluation 01 measured 4
visible passes against 3 hidden passes in the baseline, so the proxy overstated
by one in ten. Any use of it as reward must report that gap.

The hidden tests stay in the evaluation set only. They are never a training
signal, never shown to the model, and never used to filter training data that the
same fixtures later evaluate.

## E. Reserving unseen tasks

Evaluation 01's outcomes are observed, so its ten fixtures are now development
and validation data. Roughly 47 families are burned: cart-total, sorted-unique,
the 35 across SFT v1, v2 and v3, and the 10 from Evaluation 01.

For a future claim, author a new ten-fixture Evaluation 02 **after** the training
configuration is hash-frozen, following the ordering discipline already used for
SFT v3, with families disjoint from all 47. Keep the same visible-versus-hidden
test separation, which proved its worth here.

The three Hall physics tasks have never been training or validation data and
have only ever been graded against reference solutions. They stay reserved as a
separate downstream assessment under the existing Hall policy.

## Recommendation: one smallest viable experiment

**LoRA SFT of the 7B on scripted demonstrations of the complete workflow, with
evidence-supported finish as the first objective.**

The target is the one failure that is universal across every episode ever run:
the agent has never executed the shipped test after its last edit and then
finished citing the result. The baseline is **0/10**, a clean floor where any
non-zero result is visible.

- **Data**: 12 to 16 scripted, tool-executed demonstrations of read, edit, run the
  workspace test, finish citing the observed output. The v3 builder already
  produces exactly this shape, and no model generation is involved.
- **Training**: batch 1, seq ≤1024, grad checkpoint, rank 8, Q/V on the last 4
  layers, two complete passes. Estimated 5.5 GB peak MLX and 40 to 75 minutes.
- **First measurable objective**: evidence-supported finish on the ten
  Evaluation 01 fixtures, against a measured baseline of 0/10.
- **Secondary, reported separately**: independent functional repair, baseline
  3/10, with no expectation of improvement and no pooling with the primary.
- **Effort**: extend the SFT model pin to the 7B, author the demonstrations,
  train once, evaluate once.

Why not functional repair as the objective: at 3/10 with ten fixtures, a change
of one or two is indistinguishable from noise, so the experiment could not
conclude anything either way.

Two risks to state up front. A model trained to finish with evidence may finish
more and repair no better, which would be a real and reportable behavioural
result but not a capability gain. And training on scripted demonstrations of a
workflow the base model never performs may simply not transfer, as the two prior
SFT rounds did not.
