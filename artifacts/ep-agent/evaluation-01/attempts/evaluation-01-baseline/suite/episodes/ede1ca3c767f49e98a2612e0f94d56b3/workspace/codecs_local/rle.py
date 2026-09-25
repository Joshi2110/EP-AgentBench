def encode_runs(items):
    encoded = []
    for item in items:
        if encoded and encoded[-1][0] == item:
            encoded[-1][1] += 1
        else:
            encoded.append([item, 1])
    return encoded
