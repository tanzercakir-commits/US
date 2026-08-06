// cs: ensures result == x
long long identity64(long long x) { return x; }

// cs: ensures result == x + 1
long long widen_and_add(int x) { return x + 1LL; }

// cs: requires x == 4294967296
// cs: ensures result == 0
int narrow64(long long x) { return x; }

// cs: requires x < 9223372036854775807
// cs: ensures result > x
long long increment64(long long x) { return x + 1LL; }

// cs: ensures result == x / 3
long long divide64(long long x) { return x / 3LL; }

// cs: ensures result == x % 3
long long remainder64(long long x) { return x % 3LL; }

// cs: ensures result == x
long long call64(long long x) {
    long long value = identity64(x);
    return value;
}

// cs: requires n >= 0
// cs: ensures result == n
long long count64(long long n) {
    long long i = 0LL;
    // cs: invariant i >= 0
    // cs: invariant i <= n
    while (i < n) {
        i = i + 1LL;
    }
    return i;
}
