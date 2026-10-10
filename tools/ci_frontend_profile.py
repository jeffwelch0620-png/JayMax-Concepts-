"""Print public native build flags from the reviewed map; no secrets or connections."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'backend/deployment_readiness.py').read_text(encoding='utf-8-sig'))
features = next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'FEATURES')
print('REACT_APP_USE_PG=true')
for browser, _dependencies in features.values():
    if not re.fullmatch(r'[A-Z_]+', browser):
        raise ValueError('Unexpected frontend feature name')
    print(f'REACT_APP_{browser}=true')
