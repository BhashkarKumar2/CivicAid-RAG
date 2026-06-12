from app.eligibility import evaluate_eligibility
from app.models import CitizenProfile, Scheme


def check_eligibility(profile: CitizenProfile, scheme: Scheme) -> dict:
    return evaluate_eligibility(profile, scheme)

