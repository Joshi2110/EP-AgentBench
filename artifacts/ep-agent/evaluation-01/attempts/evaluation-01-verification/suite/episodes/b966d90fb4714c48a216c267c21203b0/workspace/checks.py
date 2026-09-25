from numerals.convert import to_roman as F
from numerals.meta import scheme
assert F(4) == "IV"
assert F(3) == "III"
assert scheme() == "roman"
print('PASS roman-numeral')
