#!/usr/bin/env python3

from th06.agent import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        __import__("traceback").print_exc()
        print(f"error: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)
