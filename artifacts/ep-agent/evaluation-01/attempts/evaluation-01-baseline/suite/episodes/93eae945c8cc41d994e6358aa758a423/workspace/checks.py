from net.backoff import delays as F
from net.policy import strategy
assert F(5, 1, 4) == [1, 2, 4, 4, 4]
assert F(0, 1, 100) == []
assert strategy() == "exponential"
print('PASS retry-backoff')