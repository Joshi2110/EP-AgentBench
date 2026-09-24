from sequences.streak import longest_true_run
assert longest_true_run([True,True,False,True]) == 2
assert longest_true_run([]) == 0
print('PASS true-streak')
