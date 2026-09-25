from syntax.brackets import is_balanced as F
from syntax.tokens import opener
assert F("(a[b]{c})") is True
assert F(")(") is False
assert opener() == "("
print('PASS bracket-balance')
