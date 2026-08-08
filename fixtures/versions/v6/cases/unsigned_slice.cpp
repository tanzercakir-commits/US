// cs: ensures result == 0
unsigned int wrap32() { return 4294967295u + 1u; }

// cs: ensures result == 0
unsigned long long wrap64() {
    return 18446744073709551615ULL + 1ULL;
}

// cs: requires x == -1
// cs: ensures result == -1
unsigned int from_signed(int x) {
    unsigned int value = x;
    return value;
}

// cs: requires x == -1
// cs: requires y == 0
// cs: ensures result == false
bool mixed_less(int x, unsigned int y) { return x < y; }

// cs: requires x == 2
// cs: requires y == 3
// cs: ensures result == 6
long long mixed_product(unsigned int x, long long y) { return x * y; }

// cs: requires b != 0
// cs: ensures result == a / b
unsigned long long divide64(unsigned long long a, unsigned long long b) {
    return a / b;
}

// cs: requires b != 0
// cs: ensures result == a % b
unsigned long long remainder64(unsigned long long a, unsigned long long b) {
    return a % b;
}

// cs: ensures result == x
unsigned long long identity64u(unsigned long long x) { return x; }

// cs: ensures result == x
unsigned long long call64u(unsigned long long x) {
    unsigned long long value = identity64u(x);
    return value;
}

// cs: ensures result == n
unsigned int count32(unsigned int n) {
    unsigned int i = 0u;
    // cs: invariant i <= n
    while (i < n) {
        i = i + 1u;
    }
    return i;
}
