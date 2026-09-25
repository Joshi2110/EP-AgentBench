"""Small cart helpers."""

def cart_total(rows):
    return sum(price for price, quantity in rows)

def label():
    return "cart"
