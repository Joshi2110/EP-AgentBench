from grids.matrix import transpose as F
from grids.shape import kind
assert F([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
assert F([]) == []
assert kind() == "grid"
print('PASS matrix-transpose')
