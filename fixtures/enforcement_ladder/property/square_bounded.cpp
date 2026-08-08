// cs: requires value >= 0
// cs: requires value <= 100
// cs: ensures result == value * value
int square_bounded(int value) {
    return value * value;
}