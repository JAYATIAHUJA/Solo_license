// Bulk discount: 10% off from the 10th item.
function discountedItems(count) {
  return count > 10 ? count - 9 : 0;
}

module.exports = { discountedItems };
