int absolute_value(const int value)
    pre(value != -2147483648)
    post(result: result >= 0 && (result == value || result == -value))
{
    contract_assert(value != -2147483648);
    if (value < 0) {
        return -value;
    }
    return value;
}