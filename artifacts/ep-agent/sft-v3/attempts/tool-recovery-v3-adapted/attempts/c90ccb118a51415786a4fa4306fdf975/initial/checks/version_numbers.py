from versions.parse import version_parts
assert version_parts('2.10.3') == (2,10,3)
assert version_parts('0') == (0,)
print('PASS version-numbers')
