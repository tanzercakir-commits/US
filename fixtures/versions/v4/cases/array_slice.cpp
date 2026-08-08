// A6.2 reviewed fixed-size, one-dimensional owned-array slice.

// cs: ensures return == 7
int constant_read() {
    int values[3] = {4, 7, 9};
    return values[1];
}

// cs: requires i >= 0 && i < 3
// cs: ensures return > 0
int symbolic_read(int i) {
    int values[3] = {4, 7, 9};
    return values[i];
}

// cs: ensures return == 2
int store_isolation() {
    int values[3] = {1, 2, 3};
    values[0] = 9;
    return values[1];
}

// cs: requires i >= 0 && i < 3
// cs: ensures return == 1
int read_after_write(int i) {
    int values[3] = {10, 20, 30};
    int previous = values[i];
    values[i] = previous + 1;
    return values[i] - previous;
}

// cs: requires i < 3
// cs: ensures return != 0
unsigned int unsigned_read(unsigned int i) {
    unsigned int values[3] = {1, 2, 3};
    return values[i];
}
