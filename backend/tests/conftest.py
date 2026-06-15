import sys
from pathlib import Path

# backend/ 를 sys.path에 추가 — config, services.* 직접 import 가능
sys.path.insert(0, str(Path(__file__).parents[1]))
