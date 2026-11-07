from agent.memory import EpisodicMemory


def test_memory_exclusions():
    m = EpisodicMemory(max_attempts_per_recipient=2)
    m.reject_recipient("a", "no valid graft patch")
    m.note_recipient_attempt("b")
    assert m.excluded_recipients() == {"a"}
    m.note_recipient_attempt("b")
    assert m.excluded_recipients() == {"a", "b"}
    m.reject_donor("d", "IK unreachable")
    assert m.excluded_donors() == {"d"}
    assert m.to_dict()["recipient_rejections"] == {"a": ["no valid graft patch"]}
