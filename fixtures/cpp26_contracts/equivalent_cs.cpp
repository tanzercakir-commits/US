void assert(bool);
// cs: requires value != -2147483648
// cs: ensures result >= 0 && (result == value || result == -value)
int absolute_value(const int value)
{
    assert(value != -2147483648);
    if (value < 0) {
        return -value;
    }
    return value;
}