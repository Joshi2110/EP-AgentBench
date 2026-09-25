from cart import cart_total, label
assert cart_total([(7, 3), (2, 4)]) == 29
assert cart_total([(5, 0)]) == 0
assert cart_total([]) == 0
assert cart_total([(3, 1)]) == 3
assert label() == "cart"
print("PASS cart-total")
