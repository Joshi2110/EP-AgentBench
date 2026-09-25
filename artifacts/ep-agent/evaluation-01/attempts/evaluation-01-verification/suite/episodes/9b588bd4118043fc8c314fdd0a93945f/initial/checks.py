from cipher.shift import shift_letters as F
from cipher.alphabet import size
assert F("xyz", 3) == "abc"
assert F("", 3) == ""
assert size() == 26
print('PASS caesar-shift')
