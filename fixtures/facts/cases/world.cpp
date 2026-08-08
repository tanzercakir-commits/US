int global_total = 0;

struct Counter {
    int value;
};

namespace math {
int normalize(int value) {
    int local = value;
    return local;
}

int normalize(bool value) {
    return value ? 1 : 0;
}
}

int store(Counter& counter, int value) {
    counter.value = math::normalize(value);
    global_total += counter.value;
    return global_total;
}

int pipeline(Counter& counter, int input) {
    return store(counter, math::normalize(input));
}

int scoped(int input) {
    {
        int temporary = input;
    }
    {
        int temporary = input + 1;
    }
    return input;
}
