// The second requirement is necessary for defined 32-bit C++ division:
// INT_MIN / -1 overflows even though the divisor is non-zero.
// cs: requires b != 0
// cs: requires !(a == -2147483648 && b == -1)
int safe_divide(int a, int b) {
    return a / b;
}

int verified_call(int x) {
    safe_divide(x, 2);
    return 0;
}

int violating_call(int x, int input) {
    safe_divide(x, input);
    return 0;
}

// cs: requires x < 2147483647
// cs: ensures result > x
int increment(int x) {
    return x + 1;
}

// This valid implication needs transitive arithmetic reasoning. The small
// checker deliberately reports unknown instead of claiming a proof.
// cs: requires x >= y
// cs: requires y >= z
// cs: ensures result >= z
int transitive_chain(int x, int y, int z) {
    return x;
}
