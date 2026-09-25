from stats.buckets import bucket_counts as F
from stats.edge import closed
assert F([4], [0, 4, 8]) == [0, 1]
assert F([], [0, 4]) == [0]
assert closed() == False
print('PASS histogram-buckets')
