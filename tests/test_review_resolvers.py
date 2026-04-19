from stock_select.review_resolvers import get_review_resolver


def test_get_review_resolver_uses_dedicated_b1_prompt() -> None:
    b1 = get_review_resolver("b1")

    assert b1.name == "b1"
    assert b1.prompt_path.endswith(".agents/skills/stock-select/references/prompt-b1.md")
    assert b1.review_history.__module__ == "stock_select.reviewers.b1"


def test_get_review_resolver_uses_default_for_hcr() -> None:
    hcr = get_review_resolver("hcr")

    assert hcr.name == "default"
    assert hcr.prompt_path.endswith(".agents/skills/stock-select/references/prompt.md")


def test_get_review_resolver_uses_b2_prompt_and_name() -> None:
    resolver = get_review_resolver("b2")

    assert resolver.name == "b2"
    assert resolver.prompt_path.endswith(".agents/skills/stock-select/references/prompt-b2.md")


def test_get_review_resolver_returns_callable_review_history() -> None:
    resolver = get_review_resolver("b1")

    assert callable(resolver.review_history)
