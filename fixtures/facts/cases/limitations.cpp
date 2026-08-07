#define TOUCH(target) (++(target))

using Value = int;

int external(int value);

int indirect(int (*function)(int), int value) {
    return function(value);
}

struct Base {
    virtual int run();
};

int invoke(Base* base) {
    return base->run();
}

int macro_write(int value) {
    TOUCH(value);
    return value;
}

int declaration_call(int value) {
    return external(value);
}

int builtin_call(int value) {
    return __builtin_abs(value);
}
