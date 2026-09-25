from money.rounding import round_cents as F
from money.currency import places
assert F("1.005") == "1.00"
assert F("2.341") == "2.34"
assert places() == 2
print('PASS banker-rounding')
