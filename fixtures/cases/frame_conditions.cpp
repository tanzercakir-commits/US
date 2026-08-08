struct Pair {
    int x;
    int y;
};

struct Inner {
    int value;
    int spare;
};

struct Outer {
    Inner inner;
    int tag;
};

// cs: modifies value
// cs: ensures value == 7
void assign_seven(int &value);

// cs: modifies pair.x
// cs: ensures pair.x == 7
void set_x(Pair &pair);

// cs: modifies left, right
// cs: ensures left == 3 && right == 4
void set_both(int &left, int &right);

// cs: modifies outer.inner.value
// cs: ensures outer.inner.value == 9
void set_nested(Outer &outer);

// cs: modifies
void inspect(const int &value);

// cs: ensures result == 7
int scalar_frame() {
    int value = 0;
    assign_seven(value);
    return value;
}

// cs: ensures result.x == 7 && result.y == input.y
Pair field_frame(Pair input) {
    set_x(input);
    return input;
}

// cs: ensures result.x == 3 && result.y == 4
Pair multiple_frame() {
    Pair pair = {0, 0};
    set_both(pair.x, pair.y);
    return pair;
}

// cs: ensures result.inner.value == 9 && result.inner.spare == input.inner.spare && result.tag == input.tag
Outer nested_frame(Outer input) {
    set_nested(input);
    return input;
}

// cs: requires input >= 0
// cs: ensures result == input
int empty_frame(int input) {
    inspect(input);
    return input;
}
