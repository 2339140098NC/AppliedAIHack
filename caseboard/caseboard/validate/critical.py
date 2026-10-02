"""Named findings for the stories the case home should show."""

from caseboard.domain.enums import Severity
from caseboard.domain.models import Facet, Finding, Segment, TimelineEvent
from caseboard.validate.emit import when_distinct, when_incomplete, when_present
from caseboard.validate.stories import (
    addresses,
    chest,
    defense,
    draft,
    imagers,
    index_numbers,
    location,
    missing_documents,
    nofault,
    report_dates,
    scene,
    ssn,
)

CRITICAL_GLANCE = {
    "critical_address": "Addresses disagree",
    "critical_location": "Location disagrees",
    "critical_scene": "Scene report says no injury",
    "critical_defense": "Defense exam contradicts treatment",
    "critical_index": "Two index numbers",
    "critical_report_dates": "Expert report has two dates",
    "critical_dob": "Date of birth is blank",
    "critical_nofault": "No-fault number is blank",
    "critical_ssn": "Social Security number is visible",
    "critical_hipaa_share": "HIPAA forms disagree",
    "critical_hipaa_special": "Special-category initials",
    "critical_draft": "Draft pleading in a medical file",
    "critical_chest": "2018 chest x-ray",
    "critical_imagers": "Imagers missing from HIPAA",
    "critical_pronoun": "Plaintiff called her",
    "critical_missing": "Documents named but missing",
}

CRITICAL_PHRASES = {
    "critical_address": "addresses disagree",
    "critical_location": "the accident location disagrees",
    "critical_scene": "the scene report disagrees with later treatment",
    "critical_defense": "the defense exam contradicts the treating injuries",
    "critical_index": "two index numbers are in the file",
    "critical_report_dates": "an expert report carries two dates",
    "critical_dob": "a date of birth is blank",
    "critical_nofault": "the no-fault claim number is blank",
    "critical_ssn": "part of a Social Security number is visible",
    "critical_hipaa_share": "two HIPAA forms disagree on sharing",
    "critical_hipaa_special": "special-category initials must stay off provider views",
    "critical_draft": "a draft pleading sits inside a medical bundle",
    "critical_chest": "a 2018 chest x-ray is outside the authorization window",
    "critical_imagers": "imagers are missing from the HIPAA provider list",
    "critical_pronoun": "a defense calls the plaintiff her",
    "critical_missing": "documents are mentioned but not in the file",
}


def critical_findings(
    facets: list[Facet],
    events: list[TimelineEvent],
    segments: list[Segment],
) -> list[Finding]:
    """One plain-language finding per story the stored facets support."""
    by_key: dict[str, list[Facet]] = {}
    for facet in facets:
        by_key.setdefault(facet.facet_key, []).append(facet)
    made = [
        addresses(by_key.get("patient.address", [])),
        location(by_key.get("accident.location", [])),
        scene(by_key, events),
        defense(by_key),
        index_numbers(by_key),
        report_dates(by_key.get("expert.report_date", [])),
        when_incomplete("critical_dob", "Date of birth is blank on a document that others fill in", "Other documents state a date of birth.", by_key.get("patient.date_of_birth", []), "patient.date_of_birth"),
        nofault(by_key.get("benefits.nofault", [])),
        ssn(facets),
        when_distinct("critical_hipaa_share", Severity.sensitive, "Two HIPAA authorizations disagree on sharing", "The forms do not allow the same redisclosure.", by_key.get("hipaa.redisclosure", []), "hipaa.redisclosure"),
        when_present("critical_hipaa_special", Severity.sensitive, "Keep the special-category authorization out of every provider view", "Initials cover HIV, mental health, or alcohol and drug treatment.", by_key.get("hipaa.special_categories", [])),
        draft(facets, segments),
        chest(facets, events),
        imagers(by_key),
        when_present("critical_pronoun", Severity.conflict, "Affirmative defenses call the plaintiff her", "The wording is template boilerplate.", by_key.get("draft.pronoun", [])),
        missing_documents(by_key.get("missing_document", [])),
    ]
    return [item for item in made if item is not None]
