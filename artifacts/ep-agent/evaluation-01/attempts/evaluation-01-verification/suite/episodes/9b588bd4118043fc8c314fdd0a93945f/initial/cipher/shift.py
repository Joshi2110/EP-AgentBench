def shift_letters(text, amount):
    return "".join(chr(ord(c) + amount) for c in text)
