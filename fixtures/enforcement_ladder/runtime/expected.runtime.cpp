// codeskeptic.runtime-wrapper/v1
// Generated deterministically; state: runtime_guarded, not verified.
[[noreturn]] void codeskeptic_contract_failure(
    const char* target_id,
    const char* kind,
    const char* expression
);

// target: sha256:9ebbc9a2cd7c8ff5d960a5c59a6dd593aa183ed3d2695121160f3a21fa1d1e87
int square_bounded(int value);

int codeskeptic_checked_square_bounded_9ebbc9a2cd7c(int value) {
    if (!(value >= 0)) {
        codeskeptic_contract_failure(
            "sha256:9ebbc9a2cd7c8ff5d960a5c59a6dd593aa183ed3d2695121160f3a21fa1d1e87",
            "requires",
            "value >= 0"
        );
    }
    if (!(value <= 100)) {
        codeskeptic_contract_failure(
            "sha256:9ebbc9a2cd7c8ff5d960a5c59a6dd593aa183ed3d2695121160f3a21fa1d1e87",
            "requires",
            "value <= 100"
        );
    }
    const int result = square_bounded(value);
    if (!(result == value * value)) {
        codeskeptic_contract_failure(
            "sha256:9ebbc9a2cd7c8ff5d960a5c59a6dd593aa183ed3d2695121160f3a21fa1d1e87",
            "ensures",
            "result == value * value"
        );
    }
    return result;
}
