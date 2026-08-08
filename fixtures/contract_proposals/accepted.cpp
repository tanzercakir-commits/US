// cs: ensures result >= 0
int clamp_nonnegative(int value) {
  if (value < 0) {
    return 0;
  }
  return value;
}
