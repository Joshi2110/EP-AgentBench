# cart-total development episodes: frozen

Four 7B episodes were run on the `cart-total` fixture. **This fixture is now
closed.** No further episodes, no rescoring, no alteration of the four archives.

All four are **development evidence**: engineering smoke tests on a single
fixture, each run after a fix made in response to the previous failure. They are
not a benchmark, not a controlled comparison, and not generalization evidence.
No causal claim about any individual intervention follows from them.

| # | Archive | Outcome |
| --- | --- | --- |
| 1 | `../7b-development-smoke/` | Five edits, unimportable file, `IndentationError`, no tests, no finish |
| 2 | `../7b-verification-smoke/` | Renamed the required function, ad-hoc self-test, finished claiming success |
| 3 | `../7b-contract-smoke/` | Malformed envelope three times, no edit applied, workspace unchanged |
| 4 | `../7b-envelope-smoke/` | Envelope corrected, repair applied, **grader passed**, but not agent-verified |

Two results are easy to misreport, so they are stated explicitly here.

**Episode 4 is not a completed agent workflow.** The independent grader passed
the repair. The agent never executed the shipped `checks.py`, never recognized
its success, and never finished. Report it as a grader-passing but unverified
repair.

**The episode 3 offline counterfactual is not a repair.** Applying the rejected
call's text outside the episode passes `checks.py`. The agent applied no edit
and ran no test.

Across all four episodes the shipped test was executed **zero** times.

`freeze.json` records the fixture hash, each episode's archive path, episode id,
source commit, status and archive-manifest hash, together with the rules above.
Any future verification mechanism stays disabled for these frozen experiments.
