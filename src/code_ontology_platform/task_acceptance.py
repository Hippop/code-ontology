"""Independent executable acceptance cases for the task-priority slice.

This file runs under python -I; it does not import the platform or generator.
"""
import importlib.util
import json
import sys


def verify(source_path, expected_default):
    spec = importlib.util.spec_from_file_location("accepted_task", source_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cases = []
    def case(name, check):
        try:
            check()
            cases.append({"name": name, "passed": True})
        except Exception as error:
            cases.append({"name": name, "passed": False, "error": str(error)})
    def equal(actual, expected):
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")
    def rejects(value):
        try:
            module.Task(value)
        except ValueError:
            return
        raise AssertionError(f"accepted invalid priority {value!r}")
    case("default", lambda: equal(module.Task().priority, expected_default))
    for value in ("low", "medium", "high"):
        case("retain-" + value, lambda value=value: equal(module.Task(value).priority, value))
    for value in ("urgent", "", None, 3):
        case("reject-" + repr(value), lambda value=value: rejects(value))
    return {"cases": cases, "passed": all(item["passed"] for item in cases)}


if __name__ == "__main__":
    try:
        result = verify(sys.argv[1], sys.argv[2])
    except Exception as error:
        result = {"cases": [], "passed": False, "error": str(error)}
    print(json.dumps(result))
    sys.exit(0 if result["passed"] else 1)
