"""
Implementations for the various verification tasks.
"""


def _fail_generator(spec: "A failure specification", failures: "An iterable list of failures"):
    if failures is None:
        raise Exception("Hell")
    allowed_failures = {}
    if "counter_examples" in spec:
        for cex in spec["counter_examples"]:
            for loc in cex["locations"]:
                if loc["file"] not in allowed_failures:
                    allowed_failures[loc["file"]] = set()
                allowed_failures[loc["file"]].add(int(loc["line"]))
    if spec["correct"] and len(allowed_failures) > 0:
        raise Exception("A failure that must not happen, but has counterexamples makes no sense")
    return (fail for fail in failures if fail.error.file not in allowed_failures or fail.error.line not in allowed_failures[fail.error.file])

TASKS = {
    "no_assert_fail": lambda spec, kleedir: _fail_generator(spec, kleedir.assertion_failures),
    "no_integer_division_by_zero": lambda spec, kleedir: _fail_generator(spec, kleedir.division_failures),
    "no_invalid_deref": lambda spec, kleedir: _fail_generator(spec, kleedir.ptr_errors),
    "no_invalid_free": lambda spec, kleedir: _fail_generator(spec, kleedir.free_errors),
    "no_overshift": lambda spec, kleedir: _fail_generator(spec, kleedir.overshifts),
    "no_reach_error_function": lambda spec, kleedir: _fail_generator(spec, kleedir.abortions)
}
