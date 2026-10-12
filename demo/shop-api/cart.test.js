const test = require('node:test');
const assert = require('node:assert');
const { total } = require('./cart');
const { discountedItems } = require('./discount');
const { money } = require('./format');

test('total multiplies price by quantity', () => {
  assert.strictEqual(total([{ price: 5, qty: 2 }, { price: 1, qty: 3 }]), 13);
});

test('the 10th item is already discounted', () => {
  assert.strictEqual(discountedItems(10), 1);
});

test('money formats cents', () => {
  assert.strictEqual(money(1234), '$12.34');
});
