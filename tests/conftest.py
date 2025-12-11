"""Pytest configuration for E2E tests"""


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Skip cleanup of test documents after E2E tests (for debugging)"
    )
