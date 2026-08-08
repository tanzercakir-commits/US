// A6.3 reviewed aggregate-by-value struct slice.

struct Pair {
    int x;
    int y;
};

struct Box {
    Pair pair;
    int values[2];
};

// cs: ensures return.x == x && return.y == y
Pair make_pair(int x, int y) {
    Pair result = {x, y};
    return result;
}

// cs: requires input.x < 2147483647
// cs: ensures return == input.x
int copy_isolation(Pair input) {
    int original = input.x;
    Pair copy = input;
    copy.x = copy.x + 1;
    return input.x;
}

// cs: requires i >= 0 && i < 2
// cs: ensures return == replacement
int nested_update(Box input, int i, int replacement) {
    input.pair.x = replacement;
    input.values[i] = input.pair.x;
    return input.values[i];
}

// cs: ensures return.x == input.x && return.y == input.y
Pair copy_call(Pair input) {
    Pair result = make_pair(input.x, input.y);
    return result;
}
