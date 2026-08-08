#include "api.hpp"

int shared() {
    return 2;
}

int caller() {
    return shared();
}
