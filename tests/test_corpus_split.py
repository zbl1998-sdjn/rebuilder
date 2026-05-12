from core.data_models import BehaviorSample, TestCase, TestResult
from core.probing.corpus import CorpusSplitter


def behavior(name):
    return BehaviorSample(
        test_case=TestCase(name=name),
        observed_result=TestResult(stdout=name),
    )


def stateful_behavior(plan, step):
    return BehaviorSample(
        test_case=TestCase(name=f"{plan}_{step}"),
        observed_result=TestResult(stdout=f"{plan}:{step}"),
        tags=["stateful", f"stateful_plan:{plan}", f"stateful_step:{step}"],
    )


def test_corpus_split_is_deterministic():
    corpus = [behavior(str(i)) for i in range(10)]
    splitter = CorpusSplitter(holdout_ratio=0.3, seed="fixed")

    first = splitter.split(corpus)
    second = splitter.split(corpus)

    assert [s.test_case.name for s in first.holdout] == [s.test_case.name for s in second.holdout]
    assert len(first.holdout) == 3
    assert len(first.exploration) == 7
    assert first.adversarial == []


def test_corpus_split_keeps_small_corpus_explorable():
    split = CorpusSplitter(holdout_ratio=0.5).split([behavior("one")])

    assert len(split.exploration) == 1
    assert len(split.holdout) == 0


def test_corpus_split_keeps_stateful_plans_atomic():
    corpus = [
        behavior("regular_a"),
        *[stateful_behavior("stateful_demo", index) for index in range(4)],
        behavior("regular_b"),
        behavior("regular_c"),
    ]

    split = CorpusSplitter(holdout_ratio=0.4, seed="fixed").split(corpus)

    exploration_steps = {
        sample.test_case.name
        for sample in split.exploration
        if "stateful_plan:stateful_demo" in sample.tags
    }
    holdout_steps = {
        sample.test_case.name
        for sample in split.holdout
        if "stateful_plan:stateful_demo" in sample.tags
    }
    assert not (exploration_steps and holdout_steps)
    assert exploration_steps or holdout_steps


def test_corpus_split_handles_binary_test_case_inputs():
    corpus = [
        BehaviorSample(
            test_case=TestCase(name="binary", input_files={"input.bin": b"\x00\xff\x01"}),
            observed_result=TestResult(stdout="ok"),
        ),
        behavior("text"),
    ]

    split = CorpusSplitter(holdout_ratio=0.5, seed="fixed").split(corpus)

    assert len(split.exploration) == 1
    assert len(split.holdout) == 1
