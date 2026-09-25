from codecs_local.rle import encode_runs as F
from codecs_local.name import codec
assert F(["a", "a", "b"]) == [("a", 2), ("b", 1)]
assert F([]) == []
assert codec() == "rle"
print('PASS run-length')
