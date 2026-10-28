from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
from family_reconciliation_adapter_v421 import engine_form


def test_json_roundtrip_container_normalization_preserves_values_and_input():
    engine = {'curve': [(1, 100.), (2, 99.875)], 'ledger': [{'id': 'A', 'fees': .125}]}
    saved = json.loads(json.dumps(engine))
    before = deepcopy(saved)
    assert saved != engine
    assert engine_form(saved) == engine
    assert saved == before
