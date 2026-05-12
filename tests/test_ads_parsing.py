from agent.ads import (
    GoogleAd,
    LinkedInAd,
    MetaAd,
    TikTokAd,
    _parse_google,
    _parse_linkedin,
    _parse_meta,
    _parse_tiktok,
)


class TestParseMeta:
    def test_complete_item(self):
        items = [{
            "primary_text": "Hai gia` provato Meta Ads?",
            "headline": "Riempi l'agenda in 30gg",
            "description": "Senza chiamate fredde",
            "cta": "Iscriviti",
            "angle": "pain-focus",
            "rationale": "parla al pain del target",
        }]
        ads = _parse_meta(items)
        assert len(ads) == 1
        assert isinstance(ads[0], MetaAd)
        assert ads[0].headline == "Riempi l'agenda in 30gg"

    def test_drops_item_without_primary(self):
        items = [{"headline": "x", "cta": "Iscriviti"}]
        assert _parse_meta(items) == []

    def test_drops_item_without_headline(self):
        items = [{"primary_text": "x", "cta": "Iscriviti"}]
        assert _parse_meta(items) == []

    def test_drops_item_without_cta(self):
        items = [{"primary_text": "x", "headline": "y"}]
        assert _parse_meta(items) == []

    def test_empty_description_allowed(self):
        items = [{
            "primary_text": "x",
            "headline": "y",
            "description": "",
            "cta": "Iscriviti",
        }]
        ads = _parse_meta(items)
        assert len(ads) == 1
        assert ads[0].description == ""


class TestParseGoogle:
    def test_full_rsa(self):
        items = [{
            "headlines": ["H1", "H2", "H3"],
            "descriptions": ["D1", "D2"],
            "paths": ["one", "two"],
            "angle": "benefit",
            "rationale": "good",
        }]
        ads = _parse_google(items)
        assert len(ads) == 1
        ad = ads[0]
        assert isinstance(ad, GoogleAd)
        assert ad.headlines == ("H1", "H2", "H3")
        assert ad.paths == ("one", "two")

    def test_truncates_paths_to_two(self):
        items = [{
            "headlines": ["H"],
            "descriptions": ["D"],
            "paths": ["a", "b", "c", "d"],
        }]
        ads = _parse_google(items)
        assert ads[0].paths == ("a", "b")

    def test_no_paths_ok(self):
        items = [{
            "headlines": ["H"],
            "descriptions": ["D"],
        }]
        ads = _parse_google(items)
        assert ads[0].paths == ()

    def test_drops_if_no_headlines(self):
        items = [{"descriptions": ["D"]}]
        assert _parse_google(items) == []

    def test_drops_if_no_descriptions(self):
        items = [{"headlines": ["H"]}]
        assert _parse_google(items) == []


class TestParseTikTok:
    def test_complete(self):
        items = [{
            "hook": "Ho perso 12k prima di capirlo",
            "body": "Lascia che ti racconti come.",
            "cta_verbal": "Link in bio per saperne di piu`",
            "caption": "Storia vera, scorri il video",
            "hashtags": ["marketing", "imprenditori"],
            "angle": "storytelling",
            "rationale": "pattern interrupt",
        }]
        ads = _parse_tiktok(items)
        assert len(ads) == 1
        assert isinstance(ads[0], TikTokAd)
        assert ads[0].hashtags == ("marketing", "imprenditori")

    def test_drops_without_hook(self):
        assert _parse_tiktok([{"body": "x"}]) == []

    def test_drops_without_body(self):
        assert _parse_tiktok([{"hook": "x"}]) == []


class TestParseLinkedIn:
    def test_complete(self):
        items = [{
            "headline": "Per CEO B2B con team commerciale",
            "body": "Ecco un dato di settore poco discusso...",
            "cta": "Per saperne di piu`",
            "angle": "dato-contro-intuitivo",
            "rationale": "qualifica + dato",
        }]
        ads = _parse_linkedin(items)
        assert len(ads) == 1
        assert isinstance(ads[0], LinkedInAd)

    def test_drops_partial(self):
        assert _parse_linkedin([{"headline": "x"}]) == []
        assert _parse_linkedin([{"body": "x"}]) == []
        assert _parse_linkedin(
            [{"headline": "x", "body": "y"}]  # manca cta
        ) == []
