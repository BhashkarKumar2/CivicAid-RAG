from .models import CitizenProfile, Scheme


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def state_matches(profile_state: str | None, scheme_states: list[str]) -> bool | None:
    if not profile_state:
        return None
    states = [normalize(state) for state in scheme_states]
    return "all india" in states or normalize(profile_state) in states


def list_matches(value: str | None, allowed: list[str]) -> bool | None:
    if not value:
        return None
    normalized_value = normalize(value)
    normalized_allowed = [normalize(item) for item in allowed]
    return normalized_value in normalized_allowed


def evaluate_eligibility(profile: CitizenProfile, scheme: Scheme) -> dict:
    rules = scheme.eligibility
    checks: list[dict] = []

    def add_check(name: str, passed: bool | None, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})

    min_age = rules.get("min_age")
    max_age = rules.get("max_age")
    if profile.age is None:
        add_check("Age", None, f"Age not provided. Scheme age rule: {min_age or 0}+{f' to {max_age}' if max_age else ''}.")
    else:
        passed = profile.age >= (min_age or 0) and (max_age is None or profile.age <= max_age)
        add_check("Age", passed, f"Your age: {profile.age}. Required: {min_age or 0}+{f' to {max_age}' if max_age else ''}.")

    max_income = rules.get("max_income")
    if max_income is None:
        add_check("Income", True, "No explicit income ceiling in this dataset.")
    elif profile.income is None:
        add_check("Income", None, f"Income not provided. Scheme limit: up to Rs {max_income}.")
    else:
        add_check("Income", profile.income <= max_income, f"Your income: Rs {profile.income}. Limit: Rs {max_income}.")

    state_result = state_matches(profile.state, rules.get("states", scheme.states))
    add_check("State", state_result, f"Your state: {profile.state or 'not provided'}. Scheme states: {', '.join(scheme.states)}.")

    occupation_result = list_matches(profile.occupation, rules.get("occupation", []))
    add_check("Occupation", occupation_result, f"Your occupation: {profile.occupation or 'not provided'}. Allowed: {', '.join(rules.get('occupation', []))}.")

    allowed_categories = rules.get("categories", [])
    category_result = list_matches(profile.category, allowed_categories)
    if profile.gender and normalize(profile.gender) == "female" and "Women" in allowed_categories:
        category_result = True
    add_check("Category", category_result, f"Your category/gender: {profile.category or 'not provided'} / {profile.gender or 'not provided'}. Allowed: {', '.join(allowed_categories)}.")

    known = [check for check in checks if check["passed"] is not None]
    passed_count = sum(1 for check in known if check["passed"])
    failed_count = sum(1 for check in known if check["passed"] is False)
    unknown_count = sum(1 for check in checks if check["passed"] is None)
    score = round((passed_count / max(len(known), 1)) * 100)

    if failed_count:
        status = "unlikely"
    elif unknown_count:
        status = "possibly eligible"
    else:
        status = "likely eligible"

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "missing_fields": [check["name"].lower() for check in checks if check["passed"] is None],
    }
