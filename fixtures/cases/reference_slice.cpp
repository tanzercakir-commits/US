// A6.4 reviewed local-reference slice.

struct Pair {
    int x;
    int y;
};

// cs: ensures return == 7
int scalar_alias(int value) {
    int& alias = value;
    alias = 7;
    return value;
}

// cs: ensures return.x == 4 && return.y == input.y
Pair record_alias(Pair input) {
    Pair& alias = input;
    alias.x = 4;
    return input;
}

// cs: requires input.x <= 2147483642
// cs: ensures return == input.x + 5
int disjoint_fields(Pair input) {
    const int& left = input.x;
    int& right = input.y;
    right = 5;
    return left + right;
}

// cs: ensures (choose && return == 1) || (!choose && return == 2)
int branch_lifetime(int value, bool choose) {
    if (choose) {
        int& alias = value;
        alias = 1;
    } else {
        int& alias = value;
        alias = 2;
    }
    return value;
}
