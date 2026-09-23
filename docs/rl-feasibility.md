# Feasibility: RL fine-tuning an open-weight coding model on EP-AgentBench

Assessment only. Nothing implemented. Written against v0.5.0 at `634f08c`.

## Verdict first

A credible **SFT baseline is feasible locally**. **RL is not feasible locally at
any useful scale** and would need rented GPUs. More importantly, the current
environment is **not sufficient for a generalisation claim**: three fixed Hall
tasks with one injected defect each would be memorised, not learned. Procedural
task generation is a precondition, not an optimisation.

## Local hardware and what it implies

| Resource | Measured |
| --- | --- |
| Chip | Apple M4, 10 cores |
| Unified memory | 16 GB |
| Free disk | 49 GB |
| ML tooling | none installed: no torch, mlx, transformers, trl, peft, datasets, vllm |

16 GB unified memory is the binding constraint. It is shared between model
weights, optimiser state, activations and the OS. Practical local ceilings:

- **Inference**: up to roughly 7B at 4-bit quantisation.
- **LoRA SFT**: comfortable at 0.5B, workable at 1.5B in bf16 with short
  sequences, tight at 3B, not viable at 7B.
- **RL**: needs a policy, a reference or old-policy copy, and a rollout buffer at
  once. Even 1.5B is marginal, and throughput, not memory, is the real blocker.

## Candidate models

| Model | Local role |
| --- | --- |
| Qwen2.5-Coder-0.5B | Fast iteration, plumbing and reward-pipeline debugging |
| Qwen2.5-Coder-1.5B | Realistic local SFT target |
| Qwen2.5-Coder-7B | Rented only; the smallest size likely to do multi-file repair well |

Small coding models struggle with the actual task shape here, which is reading a
specification, locating a defect across two files, and editing in place. Below
roughly 3B, expect most rollouts to fail to produce a valid patch at all, which
makes the reward signal extremely sparse.

## Environment and reward

The grader is already a usable reward server and is cheap: a full 13-case
evaluation takes **1.0 s** for `hall-transport` and `hall-thrust` and **1.9 s**
for `hall-ionization`. Reward options, in increasing risk:

- **Binary task success**, 13/13. Cleanest, very sparse.
- **Case fraction**, passed of 13. Denser, but the cases are correlated checks of
  two coupled decisions, so it is a weak partial-credit signal and rewards
  partial repair unevenly.
- **Verification integrity**, from the Experiment 02 parser. Novel, and it would
  optimise documentation of checking rather than correctness. Only defensible as
  an auxiliary term, and only with that limitation stated.

Reward hacking is the main scientific risk. The existing adversarial tests
reject hardcoded outputs, self-consistent wrong solutions, faked agreement
between diagnostics and grid-independent wrong answers, which is the right
defence, and those tests would need to grow alongside any generated task family.

## The dataset problem

**Three fixed tasks are not enough for a generalisation claim, and no result from
them should be presented as one.** With one defect per task the policy can
memorise three patches.

Minimum requirements for a defensible study:

- **Procedural instance generation**: parameterised defect injection across
  relations, so that hundreds of distinct instances exist. Roughly 200 or more
  training instances is a reasonable floor.
- **Defect families**, not just parameter jitter: sign errors, omitted terms,
  wrong closures, unit inconsistencies, wrong discretisation.
- **Split by family and task, not by seed.** Held-out parameters test memorisation
  of a formula; held-out families test whether anything transferred. Proposed:
  train on families 1 to k on two tasks, validate on unseen parameters, test on a
  held-out family and a held-out task.
- The existing 41 attempt records are far too few and too homogeneous to serve as
  SFT data; they are 35 successes on three tasks from one model.

## Realistic staging

**SFT baseline, local.** LoRA on Qwen2.5-Coder-1.5B over generated repair
trajectories, sequences capped around 4k tokens. Purpose is a competent starting
policy and a working pipeline, not a result.

**RL method.** A critic-free method, GRPO or RLOO, since a value head roughly
doubles memory for no clear gain at this scale. Group-relative advantage over
several rollouts per instance suits a sparse binary reward.

**Why local RL fails arithmetically.** One rollout means generating a patch and
grading it. At 1.5B on an M4, expect tens of tokens per second, so a 2k-token
patch is roughly 60 to 100 s. Grading adds 1 to 2 s, which is negligible. At 8
rollouts per instance and 100 optimisation steps, that is 800 rollouts, or **20
to 22 hours** of pure generation for a single small run with no restarts. That is
a sanity check, not an experiment.

## Local versus rented

**Local**: task generation, reward server, evaluation harness, verifier and
adversarial tests, dataset construction, LoRA SFT at 0.5B to 1.5B, and a
single-digit-step RL smoke test to prove the loop closes.

**Rented**: any RL at 7B, any run needing thousands of rollouts, and batched
generation with vLLM. A single 80 GB A100 or H100 at roughly $1.50 to $2.50 per
hour puts a 24 to 48 hour run at **$50 to $120**, excluding storage and failed
runs. Budget two to three times that for the iterations a first RL attempt needs.

## Honest risks

The task family may be too narrow for transfer even after generation, since all
instances share one code skeleton. Reward is sparse and small models may never
reach it. A verification-integrity reward optimises the wrong thing if used
alone. And the served-model identity problem that affects the evaluation work
does not disappear: any comparison against a hosted baseline stays conditional.

## Recommended order

1. Run Experiment 02 on the frozen tasks. It needs no training and produces a
   real measurement.
2. Build procedural instance generation and split it by defect family. This is
   the actual blocker and it is independent of any GPU.
3. Local SFT at 1.5B to prove the pipeline end to end.
4. Only then price a rented RL run, with the generalisation split fixed in
   advance.
