// CodeSkeptic A6.12 fixed-width integer phase-gate slice.

// cs: requires x == 2
// cs: requires y == 3
// cs: ensures result == 5
long long signed_add_safe(long long x, long long y) {
    return x + y;
}

long long signed_add_overflow(long long x) {
    return x + 1;
}

// cs: requires x == 5
// cs: requires y == 3
// cs: ensures result == 2
long long signed_subtract_safe(long long x, long long y) {
    return x - y;
}

long long signed_subtract_overflow(long long x) {
    return x - 1;
}

// cs: requires x == 2
// cs: ensures result == 6
long long signed_multiply_safe(long long x) {
    return x * 3LL;
}

long long signed_multiply_overflow(long long x) {
    return x * 2LL;
}

// cs: ensures result == 0
unsigned int unsigned_wrap() {
    return 4294967295u + 1u;
}

// cs: ensures result == 4294967295
unsigned int unsigned_wrap_wrong() {
    return 4294967295u + 1u;
}

// cs: ensures result == 4294967295
unsigned int unsigned_subtract_wrap() {
    return 0u - 1u;
}

// cs: ensures result == 4294967294
unsigned int unsigned_multiply_wrap() {
    return 4294967295u * 2u;
}

// cs: requires x == 1
// cs: ensures result == -1
int signed_negation_safe(int x) {
    return -x;
}

int signed_negation_minimum(int x) {
    return -x;
}

// cs: ensures result == 4294967295
unsigned int unsigned_negation() {
    return -1u;
}

// cs: requires a == 7
// cs: ensures result == 2
int division_safe(int a) {
    return a / 3;
}

// cs: requires a == 7
// cs: ensures result == 1
int remainder_safe(int a) {
    return a % 3;
}

int division_zero(int a, int b) {
    return a / b;
}

// cs: requires a == -2147483648
// cs: requires b == -1
int division_overflow(int a, int b) {
    return a / b;
}

// cs: ensures result == true
bool signed_comparison() {
    return -1 < 0;
}

// cs: ensures result == false
bool mixed_comparison() {
    return -1 < 0u;
}

// cs: ensures result == true
bool mixed_comparison_wrong() {
    return -1 < 0u;
}

// cs: ensures result == true
bool de_morgan(unsigned int x, unsigned int y) {
    return ~(x & y) == (~x | ~y);
}

// cs: ensures result == 1
unsigned int bitwise_wrong() {
    return 240u & 15u;
}

// cs: ensures result == 0
unsigned int xor_identity(unsigned int x) {
    return x ^ x;
}

// cs: ensures result == -2147483648
int signed_left_boundary() {
    return 1 << 31;
}

unsigned int left_count_invalid(unsigned int x) {
    return x << 32;
}

int signed_left_value_invalid() {
    return 2 << 31;
}

// cs: ensures result == -2
int arithmetic_right() {
    return -8 >> 2;
}

// cs: ensures result == 1
unsigned int logical_right() {
    return 2147483648u >> 31;
}

int right_count_invalid(int x) {
    return x >> -1;
}

// cs: requires x == -1
// cs: ensures result == 4294967295
unsigned int assignment_to_unsigned(int x) {
    return x;
}

// cs: ensures result == 1
int bool_promotion() {
    return ~true + 3;
}
