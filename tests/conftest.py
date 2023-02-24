def pytest_addoption(parser):
    parser.addoption(
        "--collect-groups",
        action="store_true",
        help="Collect test groups (used by GitHub Actions)",
    )
    parser.addoption("--group", type=int, help="Integration test group number")
    parser.addoption("--mysql-charm-series", help="Ubuntu series for mysql charm (e.g. jammy)")
    parser.addoption(
        "--mysql-charm-bases-index",
        type=int,
        help="Index of charmcraft.yaml base that matches --mysql-charm-series",
    )
