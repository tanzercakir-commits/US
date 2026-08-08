#include "api.hpp"

static int adjust(int value) {
    return value + 1;
}

int add(int left, int right) {
    return left + right;
}

int evaluate(int value) {
    return adjust(add(value, 1));
}

int choose(int value) {
    return value;
}

int choose(bool value) {
    return value ? 1 : 0;
}
