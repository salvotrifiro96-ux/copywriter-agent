from agent.confirmation import ConfirmationMail, _parse_items as _parse_conf
from agent.nurturing import NurturingMail, _parse_items as _parse_nurt


class TestParseConfirmation:
    def test_full(self):
        items = [{
            "subject": "Ecco il tuo PDF",
            "preview": "L'ho appena messo nel tuo accesso",
            "body": "Ciao [Nome],\n\nGrazie per esserti iscritto.",
            "signature": "Salvo\nLMS",
            "tone": "amichevole",
            "rationale": "deliverable + tu",
        }]
        out = _parse_conf(items)
        assert len(out) == 1
        assert isinstance(out[0], ConfirmationMail)

    def test_drops_without_subject(self):
        assert _parse_conf([{"body": "x"}]) == []

    def test_drops_without_body(self):
        assert _parse_conf([{"subject": "x"}]) == []


class TestParseNurturing:
    def test_full(self):
        items = [{
            "day": 1,
            "role": "bonding",
            "subject": "Una cosa che ho imparato a 26 anni",
            "preview": "Ti racconto perche` la dico oggi",
            "body": "Ciao [Nome],\n\nMi presento brevemente.",
            "signature": "Salvo\nLMS",
            "cta": "Rispondimi: chi sei tu?",
            "rationale": "bonding via storytelling",
        }]
        out = _parse_nurt(items)
        assert len(out) == 1
        m = out[0]
        assert isinstance(m, NurturingMail)
        assert m.day == 1
        assert m.role == "bonding"

    def test_day_defaults_to_zero(self):
        items = [{"subject": "x", "body": "y"}]
        out = _parse_nurt(items)
        assert out[0].day == 0

    def test_day_string_coerced(self):
        items = [{"day": "3", "subject": "x", "body": "y"}]
        out = _parse_nurt(items)
        assert out[0].day == 3

    def test_day_garbage_defaults_to_zero(self):
        items = [{"day": "not-a-number", "subject": "x", "body": "y"}]
        out = _parse_nurt(items)
        assert out[0].day == 0

    def test_drops_without_subject(self):
        assert _parse_nurt([{"body": "x"}]) == []

    def test_drops_without_body(self):
        assert _parse_nurt([{"subject": "x"}]) == []
