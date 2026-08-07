// codeskeptic.property-skeleton/v1
// Generated deterministically; state: property_generated_unexecuted.
// Caller supplies cases. Passing finite cases is not static proof.
#include <cassert>
#include <cstddef>

// target: sha256:9ebbc9a2cd7c8ff5d960a5c59a6dd593aa183ed3d2695121160f3a21fa1d1e87
// original referee statuses: unsupported
int square_bounded(int value);

struct codeskeptic_square_bounded_9ebbc9a2cd7c_case {
    int value;
};

template <std::size_t N>
void codeskeptic_property_square_bounded_9ebbc9a2cd7c(
    const codeskeptic_square_bounded_9ebbc9a2cd7c_case (&cases)[N]
) {
    for (const auto& test_case : cases) {
        const int value = test_case.value;
        if (!((value >= 0) && (value <= 100))) {
            continue;
        }
        const int result = square_bounded(value);
        assert((result == value * value));
    }
}
