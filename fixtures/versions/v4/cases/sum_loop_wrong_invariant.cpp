// cs: requires n >= 0 && n <= 10
// cs: ensures result >= 0 && result <= 100
int sum_zero_to_n(int n) {
    int i = 0;
    int total = 0;
    // cs: invariant i >= 0 && i <= n && total == i
    while (i < n) {
        i = i + 1;
        total = total + i;
    }
    return total;
}
