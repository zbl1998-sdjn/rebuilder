from main import build_reference_executable_and_backend


def test_build_reference_executable_and_backend_for_docker_image():
    args = type(
        "Args",
        (),
        {
            "reference_docker_image": "programbench/owner_1776_repo.abcdef0:task_cleanroom",
            "reference_executable": "/workspace/executable",
        },
    )()

    executable, backend = build_reference_executable_and_backend(args)

    assert executable.image == "programbench/owner_1776_repo.abcdef0:task_cleanroom"
    assert executable.executable_path == "/workspace/executable"
    assert backend is not None
