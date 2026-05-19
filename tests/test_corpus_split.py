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


def test_corpus_split_prefers_smaller_atomic_group_when_dimension_coverage_ties():
    corpus = [
        *[stateful_behavior("large_plan", index) for index in range(6)],
        *[stateful_behavior("small_plan", index) for index in range(2)],
        *[behavior(f"generic_{index}") for index in range(12)],
    ]

    split = CorpusSplitter(holdout_ratio=0.3, seed="2").split(corpus)
    holdout_names = {sample.test_case.name for sample in split.holdout}

    assert len(split.holdout) == 6
    assert {"small_plan_0", "small_plan_1"} <= holdout_names
    assert not any(name.startswith("large_plan") for name in holdout_names)


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


def test_corpus_split_prefers_behavior_dimension_coverage():
    corpus = [
        BehaviorSample(
            test_case=TestCase(name=f"generic_{index}"),
            observed_result=TestResult(stdout="ok"),
        )
        for index in range(12)
    ]
    corpus.extend(
        [
            BehaviorSample(
                test_case=TestCase(name="help", args=["--help"]),
                observed_result=TestResult(stdout="usage"),
            ),
            BehaviorSample(
                test_case=TestCase(name="stdin", stdin="alpha\n"),
                observed_result=TestResult(stdout="ok"),
            ),
            BehaviorSample(
                test_case=TestCase(name="file_input", args=["input.txt"], input_files={"input.txt": b"alpha"}),
                observed_result=TestResult(stdout="ok"),
            ),
            BehaviorSample(
                test_case=TestCase(name="error", args=["--bad"]),
                observed_result=TestResult(stderr="bad flag", exit_code=2),
                tags=["error_mode"],
            ),
        ]
    )

    split = CorpusSplitter(holdout_ratio=0.25, seed="fixed").split(corpus)

    assert {sample.test_case.name for sample in split.holdout} == {
        "help",
        "stdin",
        "file_input",
        "error",
    }


def test_corpus_split_prefers_smoke_contract_axis_coverage():
    corpus = [
        BehaviorSample(
            test_case=TestCase(
                name=f"generic_stdin_{index}",
                stdin="alpha\n",
                description="generic stdin probe",
            ),
            observed_result=TestResult(stdout="ok"),
        )
        for index in range(12)
    ]
    corpus.extend(
        [
            BehaviorSample(
                test_case=TestCase(
                    name="csv_quoted_fields",
                    stdin='name,note\nAda,"x,y"\n',
                    description="smoke_contract:csv_table.quoted_fields",
                ),
                observed_result=TestResult(stdout="ok"),
            ),
            BehaviorSample(
                test_case=TestCase(
                    name="csv_explicit_stdin",
                    args=["-"],
                    stdin="name\nAda\n",
                    description="smoke_contract:csv_table.explicit_stdin",
                ),
                observed_result=TestResult(stdout="ok"),
            ),
            BehaviorSample(
                test_case=TestCase(
                    name="csv_file_input",
                    args=["input.csv"],
                    input_files={"input.csv": b"name\nAda\n"},
                    description="smoke_contract:csv_table.file_input",
                ),
                observed_result=TestResult(stdout="ok"),
            ),
        ]
    )

    split = CorpusSplitter(holdout_ratio=0.2, seed="fixed").split(corpus)

    assert {sample.test_case.name for sample in split.holdout} == {
        "csv_quoted_fields",
        "csv_explicit_stdin",
        "csv_file_input",
    }
