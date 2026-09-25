from ranges.merge import merge_spans as F
from ranges.labels import unit
assert F([(1, 3), (2, 5)]) == [(1, 5)]
assert F([]) == []
assert unit() == "span"
print('PASS interval-merge')
