"""Materialize the executable reference controller from its parsed source tree."""
import ast
from pathlib import Path

source = Path(__file__).with_name("controller_source.py").read_text()
tree = ast.parse(source)
compile(tree, "controller.py", "exec")
target = Path("/app/submission/controller.py")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(ast.unparse(tree) + "\n")
