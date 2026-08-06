import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.party_files.evaluate_approval_dataset import evaluate_dataset


DATASET = Path("/Users/mac/Documents/党务文件/party-approval-test-dataset")


def test_party_approval_golden_dataset_is_consistent():
    report = evaluate_dataset(DATASET)
    assert report["total"] == 30
    assert report["failed"] == 0, json.dumps(report, ensure_ascii=False)
