// cs: requires candidate >= 0
// cs: ensures result == candidate
int validate(int candidate) {
    return candidate;
}

// cs: requires amount >= 0
// cs: requires balance >= amount
// cs: ensures result >= 0
int withdraw(int balance, int amount) {
    int remaining = balance - amount;
    int checked = validate(remaining);
    return checked;
}

int unchecked_validate(int candidate) {
    int checked = validate(candidate);
    return checked;
}
