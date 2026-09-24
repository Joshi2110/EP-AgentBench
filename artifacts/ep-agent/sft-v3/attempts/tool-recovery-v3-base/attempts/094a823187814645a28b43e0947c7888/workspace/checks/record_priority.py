from records import order_records
a={'name':'b','priority':1}
b={'name':'a','priority':2}
c={'name':'c','priority':1}
assert order_records([a,b,c]) == [a,c,b]
assert order_records([]) == []
print('PASS record-priority')
