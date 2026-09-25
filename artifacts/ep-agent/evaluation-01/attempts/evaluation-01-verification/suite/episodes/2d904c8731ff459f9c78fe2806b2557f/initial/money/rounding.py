def round_cents(text):
    return "%.2f" % (int(float(text) * 1000 + 5) / 1000)
