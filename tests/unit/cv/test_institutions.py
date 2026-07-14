"""Unit tests for jobfit.cv.institutions."""

import textwrap

from jobfit.cv.institutions import (
    build_edu_inst_token_map,
    build_education_institution_index,
    parse_education_institutions,
    redact_education_institutions,
)
from jobfit.cv.privacy import anonymize_for_llm


_CV_EDUCATION = textwrap.dedent("""\
    EDUCATION & CERTIFICATIONS
    Bachelor of Informatics and Computer Science                                  Sept 2011 - Jun 2014
    Moscow State University of Equipment and Computer Science                     Moscow, Russia
    Specialization: Computer Systems and Networks (230101)
    Certifications:
       CKA (2020)
    LANGUAGES
""")


def test_parse_education_institutions() -> None:
    entries = parse_education_institutions(_CV_EDUCATION)
    assert len(entries) == 1
    assert "Moscow State University" in entries[0].institution
    assert "2011" in entries[0].period


def test_redact_education_institutions_uses_placeholders() -> None:
    result = redact_education_institutions(_CV_EDUCATION)
    education = result.split("LANGUAGES")[0]
    assert "Moscow State University" not in education
    assert "[EDU_INST_1]" in education


def test_build_edu_inst_token_map() -> None:
    token_map = build_edu_inst_token_map(_CV_EDUCATION)
    assert "[EDU_INST_1]" in token_map
    assert "Moscow State University" in token_map["[EDU_INST_1]"]


def test_build_education_institution_index_maps_periods() -> None:
    index = build_education_institution_index(_CV_EDUCATION)
    assert "Moscow State University" in index["2011-2014"]


def test_anonymize_for_llm_redacts_education_institutions() -> None:
    text = textwrap.dedent("""\
        JOHN DOE
        Berlin | john@example.com
        EDUCATION
        Bachelor of Science                                       Sept 2011 - Jun 2014
        Moscow State University                                   Moscow, Russia
    """)
    result = anonymize_for_llm(text)
    assert "Moscow State University" not in result
    assert "[EDU_INST_1]" in result
    assert "[EDU_LOC_1]" in result
