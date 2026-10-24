import apparatica
import judge


def test_package_is_importable() -> None:
    assert apparatica.__doc__


def test_judge_path_dependency_is_installed() -> None:
    assert judge.__doc__
