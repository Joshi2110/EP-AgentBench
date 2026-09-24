# Preserved SFT v3 and offline edit forensics

**Frozen recovery remains base 0/4, v3 0/4.** The original experiment is unchanged and has not been rescored during this investigation. The archived [original report](sft-runs/controlled-v3-experiment/report.md) and [paired results](sft-runs/controlled-v3-experiment/result.json) retain their historical interpretation and timestamps. Statements there about results being uncommitted describe that earlier time; local archival was subsequently authorized.

## Preservation policy

`scripts/archive_sft_v3.py` verifies all 138 files in the original inventory, all base-model hashes and the three v3 adapter checkpoints. Its explicit allowlist archives 107 files: all eight complete trajectories, conversations, reports, diffs and initial/final workspaces; suite reports; frozen report/analysis; training reports, losses and configuration; execution commands/logs; software/model/dataset identities; verification records; and the original artifact inventory.

[archive-manifest.json](archive-manifest.json) records raw and archived SHA-256 hashes and every transformation. The absolute repository prefix becomes `<REPOSITORY>`; the unrelated `prior_processes` field is removed from preflight metadata. All model-visible event content, token IDs, numerical measurements and original scores are unchanged. No event is omitted. Raw artifacts remain intact in ignored `attempts/tool-recovery-v3-{base,adapted}/` and `sft-runs/controlled-v3-experiment/`. Archive-relative paths mirror repository-relative original paths. Old v1/v2 artifacts and the publication snapshot are untouched.

Exclude weights/tokenizer payloads, credentials, authentication files, temporary control directories/canary contents, protected-machine file lists and unrelated process state. This archive is for the private research repository, not the publication snapshot or wheel. The globally ignored `sft-runs` archive subtree is intentionally staged using only the manifest allowlist. Do not recursively force-add raw run directories.

Actual adapter weights remain separately at `sft-runs/tool-use-lora-v3/`, unchanged:

| File | SHA-256 |
| --- | --- |
| adapters.safetensors; 0000138_adapters.safetensors | 4f0f3dde55d6486313f860eaf1f6fcdb2d1f1373b481553e8302cacdb6bc42ff |
| 0000069_adapters.safetensors | 56522326905f73ebb08c4ce5f781368b3fe000b736779ac4df911e362ff5dded |
| adapter_config.json | 134bdad3e25e685963ee6bf1a660228981515b53d6bcf7d54efbdea7947de12e |

Retain the adapter and configuration together in private local storage/backups; Git alone cannot recover weights. A separately authorized future load uses the pinned base model with MLX-LM 0.31.3, `load('.epagent-models/qwen2.5-coder-1.5b-4bit', adapter_path='sft-runs/tool-use-lora-v3', tokenizer_config={'trust_remote_code': False})`, after checking hashes. No model was loaded for this investigation.

## Exhaustive failure taxonomy

[edit-failures.json](edit-failures.json) has **one row for each of 54 rejected model edits**. Each row contains arm, fixture, episode, turn, call/result event IDs, path, the exact latest source observation (including setup provenance), generated old_text/new_text, occurrence count, failure class, next action and subsequent edit, and explicit counterfactual corrections/results. `scripts/analyze_sft_v3_edits.py` derives it using recorded evidence and pure string/AST operations. It never invokes a model, tool, edited program or scorer.

| Cause | Base | V3 | Total | Matches of generated old_text |
| --- | ---: | ---: | ---: | ---: |
| Indentation: two spaces instead of observed four | 12 | 12 | 24 | 0 |
| Quoting: double instead of observed single quotes | 6 | 6 | 12 | 0 |
| Duplicated span: `    return 0\n` | 12 | 6 | 18 | 2 |
| Other whitespace, wrong content, wrong file, other | 0 | 0 | 0 | — |
| **Total** | **30** | **24** | **54** | **36 zero; 18 multiple; none unique** |

`exclusive-members` and `record-priority` account for indentation failures. `version-numbers` accounts for quote failures: the two quote styles express the same Python string, but are different file bytes. `true-streak` contains the identical return line in two functions. No path mismatch, stale observed source, truncation or encoding mismatch was found. Forty-two attempts follow a model-generated source read; the twelve base true-streak edits have only the injected setup read as their latest observation.

All 54 argument dictionaries exactly repeat the injected failed edit. All 54 proposed new_text strings equal the entire observed source file. This is evidence of repetition of the supplied operation, not evidence that the model diagnosed any underlying code defect.

| Action after rejection | Base | V3 | Total |
| --- | ---: | ---: | ---: |
| Reread the same unchanged source | 15 | 20 | 35 |
| Immediately repeat the rejected edit | 11 | 0 | 11 |
| No next action: budget ends | 4 | 4 | 8 |

Reinspection is a procedurally relevant response, but all 35 rereads are followed by the unchanged edit arguments. **Zero of the 46 rejected edits with a subsequent action leads to changed edit arguments.** The records cannot reveal internal reasoning, deliberate avoidance, or an intended scientific repair.

## Executability is separate from replacement scope and correctness

For the 36 indentation/quoting failures, replacing old_text with the exact observed full source corrects only those textual differences. The current match rule would accept the operation, but unchanged new_text then yields a **no-op**. No such correction was actually executed in the experiment.

For each of the 18 duplicated-span attempts, the analysis enumerates shortest unique source-context extensions around **both** matching occurrences (minimum added characters, keeping all ties). The first occurrence becomes unique by adding one trailing newline; the second needs four preceding characters, `():\n`. Either would satisfy the current matching rule, but inserting the proposed whole-file new_text into that local span changes bytes and produces **syntactically invalid Python**. AST parsing establishes only syntax, not semantic correctness. Even more readable function-context anchors still require choosing a target and aligning replacement scope; the record does not justify silently choosing one.

A separate, explicitly nonminimal counterfactual is to use the whole file as old_text in the duplicate cases. That would be executable and a no-op. Under an explicit whole-file target assumption, all 54 proposed new_text values leave the file unchanged. It would be misleading to say that minimally fixing every old_text necessarily produces a no-op, or that making a call acceptable repairs the code.

## Demonstration exact-copy burden

| Positive edit targets | Train | Validation |
| --- | ---: | ---: |
| Count | 14 | 4 |
| old_text characters: min / median / max | 15 / 50.5 / 79 | 32 / 39.5 / 58 |
| Mean characters | 49.86 | 42.25 |
| Lines: min / median / max | 1 / 2 / 5 | 2 / 2 / 2 |
| Entire observed file | 11 | 4 |
| Uniquely matches actual observed source | 14 | 4 |
| Includes indentation / trailing newline | 14 / 14 | 4 / 4 |
| Includes quote characters | 6 | 1 |

All measured text is ASCII, so character and UTF-8 byte lengths coincide. Full histograms and per-example records are in edit-failures.json. Training has three single-line targets, nine two-line targets, one four-line target and one five-line target. No positive target is a no-op. Ten train and five validation failed edits are retained only as history; just one training history demonstrates the duplicated-span error, and none in validation does.

Evaluation old_text lengths are 13, 59, 60 and 82 characters. Their weighted median is 59 for base and 59.5 for v3; the record-priority target is only three characters longer than the longest positive training target. These are modest copy lengths. The distribution does not establish that length caused failure. Repeating identical injected arguments after observing the relevant text is stronger direct evidence than any inference about sequence-length capacity. Whole-file-heavy demonstrations also provide little coverage of selecting a unique *local* region and matching replacement scope.

## Interface assessment (conceptual; not implemented)

| Interface | What it can remove on these records | What remains | New risks / required checks |
| --- | --- | --- | --- |
| A. Exact old_text replacement | Nothing automatically; exact unique matching catches both mismatches and ambiguity | Requires copying indentation, quotes, newline and enough context; no automatic syntax or semantic check | Unique matching is not version checking: a stale substring can still match after unrelated file changes. Keep confinement and size limits. |
| B. Bounded line range with observed-version precondition | Eliminates reproducing old source characters; explicit line coordinates can disambiguate repeated text | Must select the right file/range, supply appropriately scoped new_text, use the current observation ID and react to errors | Off-by-one ranges, stale coordinates, truncation/newline boundary errors, whole-file insertion into a local range. Check an immutable observed-file version against current bytes, inclusive/exclusive bounds, allowed size and path; reject stale versions atomically. Server-issued observation IDs avoid requiring the model to generate hashes. |
| C. Structured patch with contextual anchors | Unique function/context anchors can distinguish the two return lines; typed fields can avoid free-form diff-header syntax | Exact deletion/context strings can retain indentation/quote friction; duplicate anchors and wrong replacement scope remain | Patch grammar/escaping, ambiguous or fuzzy placement, multi-hunk partial application, stale anchors, wrong function selection. Require unique contextual matches, current-version checks, all-hunks validation and atomic application. No silent fuzzy fallback. |

Offline example for B: under an explicitly chosen whole-file range (all currently observed lines) and matching observed-version precondition, the recorded new_text would be accepted as an unchanged file. This removes exact-copy friction but creates no repair. Selecting only the return-line range in true-streak while keeping its recorded new_text would instead insert a whole file into a function body and break syntax. B cannot infer the intended replacement scope.

Offline example for C: a before-anchor naming `longest_true_run` disambiguates its return line, whereas an anchor containing only `return 0` remains ambiguous. Strict patches still require the actual single-quoted `split('.')` context; forgiving quote/whitespace matching would weaken exact placement guarantees. Changing the representation does not make the repeated recorded payload scientifically useful.

The evidence therefore shows **both exact-copy friction and failure to adapt arguments/scope**. It does not establish that a new interface alone would solve recovery. Conversely, these traces do not prove that the model cannot copy observed text when misleading history is absent.

## One recommended next experiment — eight single-response diagnostic probes

Propose one small 2 × 2 × 2 experiment, **not authorized or run**:

- Fix the final v3 adapter, model revision, seed 0, temperature 0 and 768-token response budget; no training, extra seeds or replacement attempts.
- Use two already-inspected development cases: exclusive-members (indentation) and true-streak (ambiguous span). Do not create a new training dataset. This narrow probe does not cover every failure type.
- Vary editing representation: current exact replacement versus a proposed version-checked line range. Only the active editing schema is offered. The latter would require a separately approved throwaway validator, not a production-agent redesign.
- Independently vary misleading history: include versus omit the recorded rejected-call/error pair as a clearly labelled historical excerpt. Render that excerpt identically as user evidence in both interface arms, so it is not an active call to a removed tool. This is an explicit microprobe representation, not a replay or rescore of the original agent session.
- Every condition receives identical numbered current source, an observation-version ID, an explicit **whole-file replacement scope**, and the same prescribed new_text: the current source plus one harmless, fixed probe comment. Providing new_text controls code-generation demands; it does not teach or test a scientific solution. Giving the scope to both arms isolates old-source copying versus compact addressing.
- Request one edit response. Validate syntax/schema, current-source preconditions, scope and exact resulting bytes offline in scratch memory. Primary outcome: the requested bytes are produced exactly. No-op, malformed call, wrong file/range, stale version or unintended bytes fails. Record retention of injected arguments separately. Do not use Hall or frozen recovery scores.

**Interpretation:** if line-range addressing succeeds where exact replacement fails even without misleading history, that supports avoidable exact-copy friction for these conditions. If either interface fails mainly when the historical error is included, that supports susceptibility to repeated bad context. If exact replacement succeeds in clean context, a categorical inability to copy is not supported. If both fail in clean context, the problem extends beyond exact old_text matching. Failure with the unfamiliar B schema is inconclusive about its eventual trainability. Prescribed whole-file scope deliberately excludes autonomous target selection, diagnosis and scientific repair.

Freeze the eight inputs, checks and interpretation before any authorized generation; retain all outputs and report individual paired cases. The existing evidence provides no basis for claiming statistical significance. This diagnostic separates two candidate explanations with eight responses rather than committing to SFT v4, RL or an agent redesign.
