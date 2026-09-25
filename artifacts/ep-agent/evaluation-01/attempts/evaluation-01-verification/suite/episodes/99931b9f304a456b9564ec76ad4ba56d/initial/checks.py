from fsutil.paths import normalize as F
from fsutil.sep import separator
assert F("a//b") == "a/b"
assert F("a/./b") == "a/b"
assert separator() == "/"
print('PASS path-normalize')
