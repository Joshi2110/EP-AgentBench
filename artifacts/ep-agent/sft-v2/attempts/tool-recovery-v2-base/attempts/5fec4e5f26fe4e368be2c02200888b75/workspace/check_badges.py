from badges.clean import strip_badge
assert strip_badge('ID:aID:b') == 'aID:b'
assert strip_badge('aID:b') == 'aID:b'
print('PASS strip-badge')
