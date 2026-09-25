def delays(attempts, base, cap):
    return [min(base * 2 ** i, cap) for i in range(attempts)]
