import ast
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app_v2.py'


def _load_peer_helper():
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_peer_universe_total')
    mod = ast.Module(body=[node], type_ignores=[])
    ns = {}
    exec(compile(mod, str(APP), 'exec'), ns)
    return ns['_peer_universe_total']


def _batch(symbols):
    return pd.DataFrame({'Symbol': symbols})


def test_dynamic_peer_universe_no_fixed_n():
    f = _load_peer_helper()
    for n in (1, 7, 14, 19, 31):
        symbols = [f'S{i:03d}' for i in range(n)]
        parsed = {i: _batch(symbols) for i in range(1, 12)}
        assert f(parsed) == n


def test_any_batch_mismatch_has_no_validated_total():
    f = _load_peer_helper()
    symbols = ['AAA', 'BBB', 'CCC']
    for wrong_batch in (1, 6, 11):
        parsed = {i: _batch(symbols) for i in range(1, 12)}
        parsed[wrong_batch] = _batch(['AAA', 'BBB'])
        assert f(parsed) == 0


def test_ui_source_has_no_b1_authority_or_mojibake():
    s = APP.read_text(encoding='utf-8')
    assert 'expected_total = len(parsed[1])' not in s
    assert 'universe B1' not in s
    for bad in ('├', 'Γ', 'â', 'ð'):
        assert bad not in s
