Return the delay for each attempt as base doubled per attempt, never exceeding the cap. Attempt zero waits base seconds. Zero attempts produce an empty list.
Repair delays in net/backoff.py. Keep the other modules and checks.py unchanged. Read the source, make the change, run checks.py with the Python tool and report only what you observed.
