Count values into half-open buckets given ascending edges: bucket i holds values with edges[i] <= value < edges[i+1]. Values outside the edge range are not counted. Return one count per bucket.
Repair bucket_counts in stats/buckets.py. Keep the other modules and checks.py unchanged. Read the source, make the change, run checks.py with the Python tool and report only what you observed.
