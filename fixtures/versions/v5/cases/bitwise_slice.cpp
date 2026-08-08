// CodeSkeptic A6.11 bitwise and shift slice.

// cs: ensures result == (~x & 255)
int low_byte(int x) {
    return ~x & 255;
}

// cs: ensures result == true
bool de_morgan(unsigned int x, unsigned int y) {
    return ~(x & y) == (~x | ~y);
}

// cs: ensures result == (x ^ y)
unsigned long long mixed_xor(int x, unsigned long long y) {
    return x ^ y;
}

// cs: ensures result == 1
unsigned int logical_right() {
    return 2147483648u >> 31;
}

// cs: ensures result == -2
int arithmetic_right() {
    return -8 >> 2;
}

// cs: ensures result == 9223372036854775808
unsigned long long high_bit() {
    return 1ULL << 63;
}

// cs: ensures result == -2147483648
int signed_boundary() {
    return 1 << 31;
}

// cs: requires x == 1
// cs: requires n == 31
// cs: ensures result == -2147483648
int variable_boundary(int x, int n) {
    return x << n;
}

// cs: ensures result == (x & 255)
unsigned int mask(unsigned int x) {
    return x & 255;
}

// cs: ensures result == (x & 255)
unsigned int mask_caller(unsigned int x) {
    unsigned int y = mask(x);
    return y;
}
