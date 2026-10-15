from functools import cache
from pathlib import Path

import yaml

# 레포 최상위의 ontology/ontology.yaml (이 파일 기준 한 단계 위 폴더)
ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "ontology" / "ontology.yaml"


@cache
def load_questions() -> dict[str, str]:
    """온톨로지의 intents를 적힌 순서대로 읽어 {슬롯 이름: 질문 문장}으로 돌려준다."""
    with open(ONTOLOGY_PATH, encoding="utf-8") as f:
        ontology = yaml.safe_load(f)
    return {name: intent["question"] for name, intent in ontology["intents"].items()}
