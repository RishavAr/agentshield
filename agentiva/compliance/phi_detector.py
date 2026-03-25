"""
Detect Protected Health Information in agent actions.
Used by the risk scorer to increase risk when PHI-like content is present.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# SSN pattern
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Credit card patterns (basic)
CC_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

# Medical Record Number
MRN_PATTERN = re.compile(r"\bMRN[-:]?\s*\d{6,10}\b", re.IGNORECASE)

# ICD-10 diagnosis codes (simplified)
ICD10_PATTERN = re.compile(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b")

# Date of birth patterns near medical context
DOB_PATTERN = re.compile(
    r"\b(?:DOB|date of birth|born|birthday)[\s:]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.IGNORECASE,
)

DRUG_NAMES: List[str] = [
    "metformin",
    "lisinopril",
    "amlodipine",
    "metoprolol",
    "atorvastatin",
    "losartan",
    "omeprazole",
    "albuterol",
    "gabapentin",
    "sertraline",
    "hydrochlorothiazide",
    "levothyroxine",
    "acetaminophen",
    "ibuprofen",
    "amoxicillin",
    "azithromycin",
    "prednisone",
    "insulin",
    "warfarin",
    "clopidogrel",
    "furosemide",
    "pantoprazole",
    "escitalopram",
    "duloxetine",
]

MEDICAL_TERMS: List[str] = [
    "diagnosis",
    "prescription",
    "patient",
    "medical record",
    "treatment",
    "prognosis",
    "symptom",
    "condition",
    "medication",
    "dosage",
    "hospital",
    "clinic",
    "physician",
    "surgeon",
    "nurse",
    "lab result",
    "blood test",
    "x-ray",
    "mri",
    "ct scan",
    "insurance claim",
    "health plan",
    "beneficiary",
]


def detect_phi(text: str) -> Dict[str, Any]:
    """
    Detect PHI-like content in text. Returns dict with detected types and risk adjustment.
    """
    if not text:
        return {
            "has_phi": False,
            "types": [],
            "details": [],
            "count": 0,
            "risk_adjustment": 0.0,
        }

    text_lower = text.lower()
    detected: List[Dict[str, Any]] = []

    ssn_matches = SSN_PATTERN.findall(text)
    if ssn_matches:
        detected.append({"type": "SSN", "count": len(ssn_matches), "severity": "critical"})

    cc_matches = CC_PATTERN.findall(text)
    if cc_matches:
        detected.append({"type": "credit_card", "count": len(cc_matches), "severity": "critical"})

    mrn_matches = MRN_PATTERN.findall(text)
    if mrn_matches:
        detected.append(
            {"type": "medical_record_number", "count": len(mrn_matches), "severity": "high"}
        )

    icd_matches = ICD10_PATTERN.findall(text)
    if icd_matches and any(term in text_lower for term in MEDICAL_TERMS):
        detected.append({"type": "diagnosis_code", "count": len(icd_matches), "severity": "high"})

    drugs_found = [drug for drug in DRUG_NAMES if drug in text_lower]
    if drugs_found and any(term in text_lower for term in MEDICAL_TERMS):
        detected.append({"type": "prescription", "count": len(drugs_found), "severity": "high"})

    dob_matches = DOB_PATTERN.findall(text)
    if dob_matches:
        detected.append({"type": "date_of_birth", "count": len(dob_matches), "severity": "medium"})

    medical_context = sum(1 for term in MEDICAL_TERMS if term in text_lower)
    if medical_context >= 3:
        detected.append({"type": "medical_context", "count": medical_context, "severity": "medium"})

    risk_adjustment = 0.0
    for d in detected:
        sev = d["severity"]
        if sev == "critical":
            risk_adjustment += 0.4
        elif sev == "high":
            risk_adjustment += 0.3
        elif sev == "medium":
            risk_adjustment += 0.15

    risk_adjustment = min(risk_adjustment, 0.5)

    return {
        "has_phi": len(detected) > 0,
        "types": [d["type"] for d in detected],
        "details": detected,
        "count": sum(d["count"] for d in detected),
        "risk_adjustment": risk_adjustment,
    }
