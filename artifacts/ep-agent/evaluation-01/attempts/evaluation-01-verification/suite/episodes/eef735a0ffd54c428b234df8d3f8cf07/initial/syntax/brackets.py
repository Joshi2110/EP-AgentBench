PAIRS = {")": "(", "]": "[", "}": "{"}

def is_balanced(text):
    return len([c for c in text if c in "([{"]) == len([c for c in text if c in ")]}"])
