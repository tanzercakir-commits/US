// Tier 1: affine-basic, expected verified.
// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 1
int bench_affine_basic_01(int value) { return value + 1; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 2 - 2
int bench_affine_basic_02(int value) { return value * 2 - 2; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 3 + 3
int bench_affine_basic_03(int value) { return value * 3 + 3; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value - 4
int bench_affine_basic_04(int value) { return value - 4; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 5
int bench_affine_basic_05(int value) { return value * 5; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 6 + 1
int bench_affine_basic_06(int value) { return value * 6 + 1; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 7 - 2
int bench_affine_basic_07(int value) { return value * 7 - 2; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 8 + 3
int bench_affine_basic_08(int value) { return value * 8 + 3; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 9 - 4
int bench_affine_basic_09(int value) { return value * 9 - 4; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value * 10 + 5
int bench_affine_basic_10(int value) { return value * 10 + 5; }

// Tier 2: affine-counterexample, expected violated.
// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 1
int bench_affine_counterexample_01(int value) { return value * 2 + 1; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 2
int bench_affine_counterexample_02(int value) { return value * 2 + 2; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 3
int bench_affine_counterexample_03(int value) { return value * 2 + 3; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 4
int bench_affine_counterexample_04(int value) { return value * 2 + 4; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 5
int bench_affine_counterexample_05(int value) { return value * 2 + 5; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 6
int bench_affine_counterexample_06(int value) { return value * 2 + 6; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 7
int bench_affine_counterexample_07(int value) { return value * 2 + 7; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 8
int bench_affine_counterexample_08(int value) { return value * 2 + 8; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 9
int bench_affine_counterexample_09(int value) { return value * 2 + 9; }

// cs: requires value >= -100 && value <= 100
// cs: ensures result == value + 10
int bench_affine_counterexample_10(int value) { return value * 2 + 10; }

// Tier 3: path-sensitive, expected verified.
// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_01(int value) {
  if (value >= 0) { return value + 1; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_02(int value) {
  if (value >= 0) { return value + 2; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_03(int value) {
  if (value >= 0) { return value + 3; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_04(int value) {
  if (value >= 0) { return value + 4; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_05(int value) {
  if (value >= 0) { return value + 5; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_06(int value) {
  if (value >= 0) { return value + 6; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_07(int value) {
  if (value >= 0) { return value + 7; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_08(int value) {
  if (value >= 0) { return value + 8; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_09(int value) {
  if (value >= 0) { return value + 9; }
  return value;
}

// cs: requires value >= -100 && value <= 100
// cs: ensures result >= value
int bench_path_sensitive_10(int value) {
  if (value >= 0) { return value + 10; }
  return value;
}

// Tier 4: deterministic-search-frontier, expected unknown.
// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_01(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_02(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_03(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_04(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_05(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_06(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_07(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_08(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_09(int a, int b, int c, int d, int e, int f) { return 0; }

// cs: requires a == 2147483647 && b == 2147483647 && c == 2147483647 && d == 2147483647 && e == 2147483647 && f == 2147483647
// cs: ensures result == 0
int bench_search_frontier_10(int a, int b, int c, int d, int e, int f) { return 0; }
