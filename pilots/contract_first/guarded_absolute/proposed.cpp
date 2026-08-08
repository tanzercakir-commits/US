// cs: ai requires value > -2147483648
// cs: ai ensures result >= 0
// cs: ai ensures result == value || result == -value
int guarded_absolute_value(int value);
