"""Manual HDFC Securities authentication test.

Run: python -m scripts.test_hdfc_auth
"""

import asyncio

from vega.config import VegaConfig
from vega.broker.auth import HdfcAuth
from vega.utils.logging import setup_logging


async def main() -> None:
    setup_logging("DEBUG")
    config = VegaConfig.load()

    auth = HdfcAuth(config.hdfc)

    print("Initiating HDFC login...")
    try:
        request_id = await auth.initiate_login()
        print(f"OTP sent. Request ID: {request_id}")

        otp = input("Enter 6-digit OTP: ").strip()
        token = await auth.complete_login(otp)
        print(f"Login successful! Token expires at: {token.expires_at}")

    except Exception as exc:
        print(f"Auth failed: {exc}")
    finally:
        await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
