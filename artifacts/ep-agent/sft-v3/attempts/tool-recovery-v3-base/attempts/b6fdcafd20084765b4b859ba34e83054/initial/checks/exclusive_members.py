from collections_ops import only_left
assert only_left([1,2,2], [2,3]) == {1}
assert only_left([], [1]) == set()
print('PASS exclusive-members')
