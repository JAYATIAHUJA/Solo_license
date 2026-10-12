// Money formatting used across the API.
function money(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

module.exports = { money };
