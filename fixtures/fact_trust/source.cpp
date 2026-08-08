// cs: modifies
// cs: ensures result == value
int leaf(int value) {
  return value;
}

// cs: modifies
// cs: ensures result == value
int caller(int value) {
  int result_value = leaf(value);
  return result_value;
}

// cs: ensures result == value
int no_frame(int value) {
  return value;
}

// cs: modifies
int zero_obligations(int value) {
  return value;
}