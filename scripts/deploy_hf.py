"""Retired public Space uploader. This entry point never reads or uploads files."""
import sys


def main() -> int:
    print(
        "Hugging Face Space deployment is retired and unsupported. No files were read or uploaded.\n"
        "The former helper could publish local models and configuration to a public repository.\n"
        "Keep training videos, labels, annotations and trained artifacts local.\n"
        "To explicitly share the native analysis app through an HTTPS tunnel, run:\n"
        "  python scripts/serve.py start --public\n"
        "That command exposes the running analysis app; it does not upload the project to a Space.\n"
        "For local service options: python scripts/serve.py --help",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
