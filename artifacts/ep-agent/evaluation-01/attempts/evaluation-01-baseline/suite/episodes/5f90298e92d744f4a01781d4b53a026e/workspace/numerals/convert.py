VALUES = [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]

def to_roman(number):
    out = ""
    for value, sign in VALUES:
        while number >= value:
            out += sign * (number // value)
            number %= value
    return out
