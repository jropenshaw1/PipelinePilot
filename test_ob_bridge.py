"""
Tests for ob_bridge.py — parser validation against real OB entries.
Run: python -m pytest test_ob_bridge.py -v
"""

import pytest
from ob_bridge import (
    parse_qfl_block,
    parse_opportunity_artifact,
    parse_rationale,
    parse_ob_thought,
)


# ── Test Data: mirrors the three live quick-fit entries ──────

INTEPROS_CONTENT = """[quick-fit-log]
source_channel: linkedin
company_name: IntePros
role_title: Remote Director of DevSecOps
role_level: Director
location_remote_status: remote | Phoenix, AZ
opportunity_type: job
quick_fit: weak
decision: pass
primary_pass_reason: wrong-domain
[/quick-fit-log]

RATIONALE: This is a DevSecOps/security engineering leadership role requiring deep hands-on Azure DevOps and HIPAA/SOC 2/HITRUST compliance ownership. Domain gap is fundamental.

[opportunity-artifact]
We are seeking a strategic, hands-on Remote Director of DevSecOps to unify DevOps, Security, and Platform Engineering into a single high-performing function.
[/opportunity-artifact]"""

JOBGETHER_CONTENT = """[quick-fit-log]
source_channel: linkedin
company_name: Unknown (via Jobgether)
role_title: Director, Cloud Engineering & Operations, FinOps
role_level: Director
location_remote_status: remote | United States
opportunity_type: job
quick_fit: strong
decision: pursue
[/quick-fit-log]

RATIONALE: This role is nearly a mirror of Jonathan's Choice Hotels FinOps function. Domain alignment is exceptional. Degree flag noted but not a blocker.

[opportunity-artifact]
This position is posted by Jobgether on behalf of a partner company. This role leads the strategy and execution of all financial aspects of cloud operations within a high-growth SaaS environment.
[/opportunity-artifact]"""

DANDY_CONTENT = """[quick-fit-log]
source_channel: linkedin
company_name: Dandy
role_title: Director, IT
role_level: Director
location_remote_status: remote | United States
opportunity_type: job
quick_fit: moderate
decision: pass
primary_pass_reason: wrong-domain
[/quick-fit-log]

RATIONALE: Right level and location but the core is manufacturing/OT IT — not Jonathan's cloud infrastructure/FinOps differentiator.

[opportunity-artifact]
We are seeking a results-oriented and strategic Director of IT to lead and evolve our Corporate IT function, as well as drive technology operations across our Manufacturing and Supply Chain sites.
[/opportunity-artifact]"""


# ── QFL Block Parsing ────────────────────────────────────────

class TestParseQflBlock:
    def test_intepros_parses(self):
        result = parse_qfl_block(INTEPROS_CONTENT)
        assert result is not None
        assert result["company_name"] == "IntePros"
        assert result["role_level"] == "Director"
        assert result["quick_fit"] == "weak"
        assert result["decision"] == "pass"
        assert result["primary_pass_reason"] == "wrong-domain"

    def test_jobgether_parses(self):
        result = parse_qfl_block(JOBGETHER_CONTENT)
        assert result is not None
        assert result["company_name"] == "Unknown (via Jobgether)"
        assert result["quick_fit"] == "strong"
        assert result["decision"] == "pursue"
        assert result.get("primary_pass_reason") is None

    def test_dandy_parses(self):
        result = parse_qfl_block(DANDY_CONTENT)
        assert result is not None
        assert result["company_name"] == "Dandy"
        assert result["quick_fit"] == "moderate"
        assert result["decision"] == "pass"
        assert result["primary_pass_reason"] == "wrong-domain"

    def test_missing_block_returns_none(self):
        result = parse_qfl_block("Just some random text with no block")
        assert result is None

    def test_missing_required_field_returns_none(self):
        incomplete = """[quick-fit-log]
source_channel: linkedin
company_name: Acme
[/quick-fit-log]"""
        result = parse_qfl_block(incomplete)
        assert result is None

    def test_pass_without_reason_returns_none(self):
        bad = """[quick-fit-log]
source_channel: linkedin
company_name: Acme
role_title: VP Engineering
role_level: VP
location_remote_status: remote
opportunity_type: job
quick_fit: weak
decision: pass
[/quick-fit-log]"""
        result = parse_qfl_block(bad)
        assert result is None

    def test_invalid_enum_returns_none(self):
        bad = """[quick-fit-log]
source_channel: twitter
company_name: Acme
role_title: VP Engineering
role_level: VP
location_remote_status: remote
opportunity_type: job
quick_fit: strong
decision: pursue
[/quick-fit-log]"""
        result = parse_qfl_block(bad)
        assert result is None

    def test_location_with_pipe_separator(self):
        result = parse_qfl_block(INTEPROS_CONTENT)
        assert result["location_remote_status"] == "remote | Phoenix, AZ"


# ── Opportunity Artifact Parsing ─────────────────────────────

class TestParseOpportunityArtifact:
    def test_intepros_artifact(self):
        result = parse_opportunity_artifact(INTEPROS_CONTENT)
        assert result is not None
        assert "DevSecOps" in result

    def test_no_artifact_returns_none(self):
        result = parse_opportunity_artifact("No artifact here")
        assert result is None


# ── Rationale Parsing ────────────────────────────────────────

class TestParseRationale:
    def test_intepros_rationale(self):
        result = parse_rationale(INTEPROS_CONTENT)
        assert result is not None
        assert "DevSecOps" in result

    def test_no_rationale_returns_none(self):
        result = parse_rationale("No rationale here")
        assert result is None


# ── Full Thought Parsing ─────────────────────────────────────

class TestParseObThought:
    def test_full_thought_intepros(self):
        thought = {
            "id": "cecae02a-55c5-439a-8634-00b08a47a46f",
            "content": INTEPROS_CONTENT,
            "created_at": "2026-04-06T10:30:00Z",
        }
        record = parse_ob_thought(thought)
        assert record is not None
        assert record["ob_thought_id"] == "cecae02a-55c5-439a-8634-00b08a47a46f"
        assert record["company_name"] == "IntePros"
        assert record["decision"] == "pass"
        assert "opportunity_artifact" in record
        assert "notes" in record  # rationale mapped to notes

    def test_full_thought_jobgether_pursue(self):
        thought = {
            "id": "a9b6fc6f-fdce-49bd-b25a-30e348d89ed4",
            "content": JOBGETHER_CONTENT,
            "created_at": "2026-04-06T10:35:00Z",
        }
        record = parse_ob_thought(thought)
        assert record is not None
        assert record["decision"] == "pursue"
        assert record.get("primary_pass_reason") is None

    def test_timestamp_normalization(self):
        thought = {
            "id": "test-id",
            "content": JOBGETHER_CONTENT,
            "created_at": "2026-04-06T14:30:00.123456+00:00",
        }
        record = parse_ob_thought(thought)
        assert record["timestamp"] == "2026-04-06T14:30:00"

    def test_unparseable_content_returns_none(self):
        thought = {
            "id": "test-id",
            "content": "Just some random thought about lunch",
        }
        result = parse_ob_thought(thought)
        assert result is None
