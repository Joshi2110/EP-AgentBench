from maps.access import lookup_or_default
assert lookup_or_default({'a': 0}, 'a', 9) == 0
assert lookup_or_default({}, 'a', 9) == 9
print('PASS mapping-fallback')
