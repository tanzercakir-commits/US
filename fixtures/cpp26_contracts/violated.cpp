int must_increase(const int value)
    pre(value >= 0)
    post(result: result > value)
{
    contract_assert(value >= 0);
    return value;
}