"""Small cart helpers."""

def calculate_total(cart_items):
    return sum(item['price'] * item['quantity'] for item in cart_items)
    return sum(price for price, quantity in rows)

def label():
    return "cart"
