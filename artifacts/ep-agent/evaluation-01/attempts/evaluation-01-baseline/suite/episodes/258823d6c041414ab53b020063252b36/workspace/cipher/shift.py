def shift_letters(text, amount):
    shifted_text = []
    for c in text:
        shifted_text.append(chr((ord(c) - ord('a') + amount) % 26 + ord('a')))
    return ''.join(shifted_text)
