"""Small cart helpers."""

def cart_total(rows):
    return sum(price * quantity for price, quantity in rows)

def label():
    return "cart"
