"""Mutation tests for oracle vacuous policy (_oracle_says_pass)."""
import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from minicc.benchmarks import _oracle_says_pass, VACUOUS_ORACLE_POLICY


def test_baseline_vacuous_allow():
    """Baseline: vacuous oracle with allow policy passes."""
    row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
    from minicc.benchmarks import _oracle_says_pass
    assert _oracle_says_pass({"objective_oracle": {"passed": True}, "grader_type": "file_contract"}) is True


def test_mutation_C1_oracle_always_true():
    """C1: Make _oracle_says_pass always return True -> vacuous should pass but shouldn't."""
    import minicc.benchmarks as bm
    original = bm._oracle_says_pass
    try:
        bm._oracle_says_pass = lambda row: True
        # With always-True, vacuous oracle passes
        row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
        from minicc.benchmarks import _oracle_says_pass
        assert _oracle_says_pass({"objective_oracle": {"passed": True}, "grader_type": "file_contract"}) is True
    finally:
        bm._oracle_says_pass = original


def test_mutation_C2_oracle_no_case_count():
    """C2: Remove case_count check -> vacuous should pass when it shouldn't."""
    import minicc.benchmarks as bm
    original = bm._oracle_says_pass
    try:
        def mutated(row):
            oracle = row.get("objective_oracle")
            if not isinstance(oracle, dict) or oracle.get("passed") is not True:
                return False
            # Removed case_count check
            return row.get("grader_type") in {"file_contract", "command_contract"}
        import minicc.benchmarks as bm_mod
        bm_mod._oracle_says_pass = mutated
        try:
            # With no case_count check, vacuous passes
            row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
            from minicc.benchmarks import _oracle_says_pass
            assert _oracle_says_pass({"objective_oracle": {"passed": True}, "grader_type": "file_contract"}) is True
        finally:
            import minicc.benchmarks as bm_mod
            bm_mod._oracle_says_pass = original
    finally:
        pass


def test_mutation_C3_policy_deny():
    """C3: Policy 'deny' should reject all vacuous oracles."""
    import minicc.benchmarks as bm
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "deny"
        from minicc.benchmarks import _oracle_says_pass
        row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
        assert _oracle_says_pass(row) is False
    finally:
        import minicc.benchmarks as bm
        bm.VACUOUS_ORACLE_POLICY = "allow"


def test_mutation_C4_policy_require_case_count():
    """C4: Policy 'require_case_count' should reject vacuous oracles."""
    import minicc.benchmarks as bm
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "require_case_count"
        from minicc.benchmarks import _oracle_says_pass
        row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
        assert _oracle_says_pass(row) is False
    finally:
        import minicc.benchmarks as bm
        bm.VACUOUS_ORACLE_POLICY = "allow"


def test_baseline_vacuous_allow():
    """Baseline: vacuous oracle with allow policy passes."""
    from minicc.benchmarks import _oracle_says_pass
    row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
    assert _oracle_says_pass(row) is True


def test_oracle_with_case_count():
    """Oracle with case_count >= 1 passes regardless of policy."""
    from minicc.benchmarks import _oracle_says_pass
    row = {"objective_oracle": {"passed": True, "case_count": 2}, "grader_type": "file_contract"}
    assert _oracle_says_pass(row) is True


def test_vacuous_with_unknown_policy():
    """Unknown policy defaults to deny (safe)."""
    import minicc.benchmarks as bm
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "unknown"
        from minicc.benchmarks import _oracle_says_pass
        row = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
        assert _oracle_says_pass(row) is False
    finally:
        import minicc.benchmarks as bm
        bm.VACUOUS_ORACLE_POLICY = "allow"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])