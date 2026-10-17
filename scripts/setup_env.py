"""Create a private local configuration without printing its generated API key."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists; preserved without changes.")
        return
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    content = content.replace("JURY_API_KEY=", "JURY_API_KEY=" + secrets.token_urlsafe(48), 1)
    target.write_text(content, encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    print("Created ignored .env with a generated judge key. Keep it private; use your editor to retrieve it.")


if __name__ == "__main__":
    main()
