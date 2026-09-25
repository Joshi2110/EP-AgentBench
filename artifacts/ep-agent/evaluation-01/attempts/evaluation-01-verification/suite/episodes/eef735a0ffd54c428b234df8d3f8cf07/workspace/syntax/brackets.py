PAIRS = {")": "(", "]": "[", "}": "{"}

def is_balanced(text):
    stack = []
    for char in text:
        if char in PAIRS:
            stack.append(char)
        elif char in PAIRS.values():
            if not stack or PAIRS[stack.pop()] != char:
                return False
    return not stack
