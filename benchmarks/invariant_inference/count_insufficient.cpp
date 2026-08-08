// cs: requires n >= 0
// cs: ensures result == n
int count_insufficient(int n) {
  int i = 0;
  // cs: candidate
  while (i < n) {
    i = i + 1;
  }
  return i;
}