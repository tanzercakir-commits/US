// A6.7 combined semantic-extension phase-gate slice.

struct Pair {
    int x;
    int y;
};

// cs: modifies pair.x
// cs: ensures pair.x == 7
void set_x(Pair &pair);

// cs: ensures result.x == 7 && result.y == input.y
Pair preserve_frame(Pair input) {
    set_x(input);
    return input;
}

// cs: ensures result == 3
unsigned int extension_bundle() {
    int values[2] = {5, 6};
    Pair pair = {values[0], values[1]};
    int &alias = pair.y;
    alias = 7;
    set_x(pair);

    long long wide = 2147483648LL;
    long long adjusted = wide + pair.x;
    unsigned int bits = 15u & 3u;
    unsigned int i = 0u;
    // cs: invariant i <= bits
    while (i < bits) {
        i = i + 1u;
    }
    return i;
}
