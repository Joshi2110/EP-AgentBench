"""Calculate the total cost of items in the cart."""

    return sum(item['price'] * item['quantity'] for item in items)

def label():
    return "cart"
