"""Entry point: python -m vega"""

import asyncio
import sys

from .config import VegaConfig
from .engine import VegaEngine


def main() -> None:
    try:
        config = VegaConfig.load()
    except Exception as exc:
        print(f"Configuration error: {exc}")
        print("Make sure .env file exists with required values. See .env.example")
        sys.exit(1)

    engine = VegaEngine(config)

    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("\nVEGA shutting down...")


if __name__ == "__main__":
    main()
