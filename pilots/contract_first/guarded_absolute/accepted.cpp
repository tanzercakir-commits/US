// cs: requires value != -2147483648
// cs: ensures result >= 0
// cs: ensures result == value || result == -value
int guarded_absolute_value(int value);
