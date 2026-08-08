void assert(bool);

// cs: requires x >= 0
// cs: requires x <= 100
// cs: ensures result >= x
int scaling_slice(
    int x,
    bool b0,
    bool b1,
    bool b2,
    bool b3
) {
    int y = x;
    if (b0) { y = y + 1; } else { y = y + 2; }
    if (b1) { y = y + 1; } else { y = y + 2; }
    if (b2) { y = y + 1; } else { y = y + 2; }
    if (b3) { y = y + 1; } else { y = y + 2; }
    assert(y >= x);
    return y;
}
