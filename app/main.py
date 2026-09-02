"""Process entry point for the CUBIC AIHost Python MVP."""

import uvicorn

from app.bootstrap import create_app
from app.core.settings import AIHOST_HOST, AIHOST_PORT

app = create_app()


def main() -> None:
    uvicorn.run(app, host=AIHOST_HOST, port=AIHOST_PORT, log_level="info")


if __name__ == "__main__":
    main()

