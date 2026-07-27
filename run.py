from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from perfbot.main import main

if __name__ == "__main__":
    main()
