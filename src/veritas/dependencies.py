"""Conservative lexical Python dependency candidates, never executable analysis.

Resolved means a unique supported static binding, not a proven runtime call target.
Dynamic dispatch and runtime rebinding are outside this extractor's guarantee.
"""

import ast
import hashlib
import io
import os
import tokenize
from collections import Counter, defaultdict
from pathlib import Path

from .io import digest, file_hash, write_json

VERSION = "python-lexical-v1"
EXCLUDED = {".git", ".venv", ".venv-rebench", "venv", "node_modules", "__pycache__"}


class Bindings(ast.NodeVisitor):
    """Overapproximate bindings without entering nested lexical scopes."""

    def __init__(self):
        self.names = Counter()
        self.wildcard = False

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names[node.id] += 1

    def visit_FunctionDef(self, node):
        self.names[node.name] += 1

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        pass

    def visit_Import(self, node):
        for alias in node.names:
            self.names[alias.asname or alias.name.split(".")[0]] += 1

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                self.wildcard = True
            else:
                self.names[alias.asname or alias.name] += 1

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    def visit_Global(self, node):
        self.names.update(node.names)

    visit_Nonlocal = visit_Global

    def visit_MatchAs(self, node):
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        if node.rest:
            self.names[node.rest] += 1
        self.generic_visit(node)


def _bindings(body):
    result = Bindings()
    for node in body:
        result.visit(node)
    return result


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = _dotted(node.value)
        return f"{root}.{node.attr}" if root else None
    return None


def _module(path):
    parts = list(Path(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(tree, module, is_package):
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split(".")[0]] = (
                    "module", alias.name if alias.asname else alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                package = module.split(".") if is_package else module.split(".")[:-1]
                if node.level > len(package):
                    continue
                target = ".".join(package[:len(package) - node.level + 1]
                                  + ([target] if target else []))
            for alias in node.names:
                if alias.name != "*":
                    imports[alias.asname or alias.name] = ("from", f"{target}.{alias.name}")
    return imports


def _inventory(tree, path):
    entries = []

    def visit(node, parents=(), function_depth=0):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = ".".join((*parents, node.name))
            entry = {
                "id": f"{path}::{qualified}@{node.lineno}",
                "identity": f"{path}::{qualified}", "qualified_name": qualified,
                "name": node.name, "path": path, "line": node.lineno,
                "end_line": node.end_lineno, "nested": function_depth > 0,
                "method": bool(parents) and function_depth == 0,
                "decorated": bool(node.decorator_list),
                "signature_sha256": digest({
                    "args": ast.dump(node.args, include_attributes=False),
                    "returns": ast.dump(node.returns) if node.returns else None,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                }),
                "body_sha256": digest([ast.dump(n, include_attributes=False) for n in node.body]),
                "definition_sha256": digest(ast.dump(node, include_attributes=False)),
            }
            entries.append((entry, node))
            for child in node.body:
                visit(child, (*parents, node.name), function_depth + 1)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                visit(child, (*parents, node.name), function_depth)
        else:
            for child in ast.iter_child_nodes(node):
                visit(child, parents, function_depth)

    visit(tree)
    return entries


def compare_symbols(before, after):
    """Compare unique lexical identities, never infer renames or semantic equivalence."""
    old, new = defaultdict(list), defaultdict(list)
    for row in before:
        old[row["identity"]].append(row)
    for row in after:
        new[row["identity"]].append(row)
    result = []
    for identity in sorted(old.keys() | new.keys()):
        a, b = old[identity], new[identity]
        if len(a) > 1 or len(b) > 1:
            status = "ambiguous_identity"
        elif not a:
            status = "added"
        elif not b:
            status = "removed"
        elif a[0]["signature_sha256"] != b[0]["signature_sha256"]:
            status = "signature_changed"
        elif a[0]["body_sha256"] != b[0]["body_sha256"]:
            status = "body_changed"
        elif a[0]["definition_sha256"] != b[0]["definition_sha256"]:
            status = "definition_changed"
        else:
            status = "unchanged"
        result.append({"identity": identity, "status": status})
    return result


def extract_dependencies(root, max_file_bytes=1_000_000, max_files=10_000):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root must be a real directory, not a symlink")
    if max_file_bytes < 1 or max_files < 1:
        raise ValueError("Extraction limits must be positive")
    root = root.resolve()
    files, skipped, errors, parsed = [], [], [], {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs):
            p = Path(directory) / name
            if name in EXCLUDED or p.is_symlink():
                skipped.append({"path": p.relative_to(root).as_posix(),
                                "reason": "symlink" if p.is_symlink() else "excluded_directory"})
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            p = Path(directory) / name
            relative = p.relative_to(root).as_posix()
            if p.is_symlink() or not p.is_file():
                skipped.append({"path": relative, "reason": "symlink_or_special_file"})
                continue
            if len(files) >= max_files:
                raise ValueError("Python file limit exceeded; narrow the source root")
            # Bounded read; source must remain quiescent during extraction.
            with p.open("rb") as stream:
                raw = stream.read(max_file_bytes + 1)
            if len(raw) > max_file_bytes:
                raise ValueError(f"Python file exceeds byte limit: {relative}")
            files.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
            try:
                encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                tree = ast.parse(raw.decode(encoding), filename=relative)
            except (SyntaxError, UnicodeError, LookupError, RecursionError) as exc:
                errors.append({"path": relative, "reason": type(exc).__name__,
                               "line": getattr(exc, "lineno", None)})
                continue
            parsed[relative] = {
                "tree": tree, "module": _module(relative),
                "bindings": _bindings(tree.body), "inventory": _inventory(tree, relative),
            }
    modules = defaultdict(list)
    # Keep failed-parse modules in the namespace inventory: otherwise a colliding
    # valid package could appear uniquely resolvable merely because parsing failed.
    for item in files:
        modules[_module(item["path"])].append(item["path"])
    symbols, calls, edges = [], [], []

    def target(qualified):
        module, _, name = qualified.rpartition(".")
        paths = modules.get(module, [])
        if len(paths) != 1:
            return None, "external_or_ambiguous_module"
        if paths[0] not in parsed:
            return None, "target_module_parse_error"
        data = parsed[paths[0]]
        if data["bindings"].wildcard or data["bindings"].names[name] != 1:
            return None, "ambiguous_or_rebound_target"
        top = {id(n) for n in data["tree"].body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        candidates = [e for e, n in data["inventory"] if id(n) in top and e["name"] == name]
        if len(candidates) != 1:
            return None, "unsupported_target_or_reexport"
        if candidates[0]["decorated"]:
            return None, "decorated_target"
        return candidates[0], None

    for path, data in sorted(parsed.items()):
        imports = _imports(data["tree"], data["module"], Path(path).name == "__init__.py")
        bindings = data["bindings"]
        for entry, function in data["inventory"]:
            symbols.append(entry)
            local = _bindings(function.body).names
            args = function.args
            local.update(a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs])
            for arg in (args.vararg, args.kwarg):
                if arg:
                    local[arg.arg] += 1

            class Calls(ast.NodeVisitor):
                unsupported_scope = False

                def visit_FunctionDef(self, node):
                    pass

                visit_AsyncFunctionDef = visit_FunctionDef
                visit_ClassDef = visit_FunctionDef

                def scoped(self, node):
                    previous = self.unsupported_scope
                    self.unsupported_scope = True
                    self.generic_visit(node)
                    self.unsupported_scope = previous

                visit_Lambda = scoped
                visit_ListComp = scoped
                visit_SetComp = scoped
                visit_DictComp = scoped
                visit_GeneratorExp = scoped

                def visit_Call(self, node):
                    dotted = _dotted(node.func)
                    base = dotted.split(".")[0] if dotted else None
                    resolved, reason = None, None
                    if entry["nested"] or self.unsupported_scope:
                        reason = "unsupported_nested_scope"
                    elif not dotted:
                        reason = "dynamic_call_expression"
                    elif local[base]:
                        reason = "local_binding_or_dynamic_dispatch"
                    elif bindings.wildcard:
                        reason = "wildcard_import"
                    elif bindings.names[base] > 1:
                        reason = "ambiguous_or_rebound_binding"
                    elif base in imports:
                        kind, imported = imports[base]
                        suffix = dotted[len(base):]
                        qualified = imported + suffix
                        if kind == "module" and not suffix:
                            reason = "module_not_function"
                        else:
                            resolved, reason = target(qualified)
                    elif "." in dotted:
                        reason = "dynamic_or_unsupported_attribute"
                    else:
                        resolved, reason = target(f"{data['module']}.{dotted}")
                    call = {"caller": entry["id"], "path": path, "line": node.lineno,
                            "column": node.col_offset, "expression": ast.unparse(node.func)[:300],
                            "status": "static_candidate" if resolved else "unresolved",
                            "reason": reason, "callee": resolved["id"] if resolved else None}
                    calls.append(call)
                    if resolved:
                        edges.append({"prerequisite": resolved["id"], "consumer": entry["id"],
                                      "call_path": path, "call_line": node.lineno,
                                      "call_column": node.col_offset, "basis": "lexical_binding"})
                    self.generic_visit(node)

            visitor = Calls()
            for statement in function.body:
                visitor.visit(statement)
    result = {
        "schema_version": 1, "extractor": VERSION,
        "implementation_sha256": file_hash(Path(__file__)),
        "files": sorted(files, key=lambda f: f["path"]),
        "symbols": sorted(symbols, key=lambda e: (e["path"], e["line"])),
        "calls": sorted(calls, key=lambda c: (c["path"], c["line"], c["column"])),
        "edges": sorted(edges, key=lambda e: (e["call_path"], e["call_line"], e["call_column"])),
        "skipped": skipped, "errors": errors,
        "coverage": {"python_files": len(files), "parsed_files": len(parsed),
                     "functions": len(symbols), "calls": len(calls),
                     "static_candidates": len(edges), "unresolved": len(calls) - len(edges)},
        "limitations": ["Static lexical candidates, not proven runtime or causal dependencies",
                        "Choose import root explicitly (e.g. repository/src for src layouts)",
                        "No reexport, dynamic dispatch, reflection, or runtime rebinding resolution",
                        "Calls in module/class initialization, defaults, and decorators are not inventoried",
                        "Nested/lambda/comprehension call targets remain unresolved",
                        "Source must be quiescent; no git commit or repository authenticity is inferred"],
    }
    return result


def write_dependencies(root, output, max_file_bytes=1_000_000, max_files=10_000):
    output = Path(output)
    if output.exists():
        raise ValueError("Dependency output already exists; use a new directory")
    result = extract_dependencies(root, max_file_bytes, max_files)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "dependencies.json", result)
    summary = {"extractor": VERSION, "coverage": result["coverage"],
               "dependencies_sha256": file_hash(output / "dependencies.json"),
               "source_files_sha256": digest(result["files"]),
               "inference_started": False, "code_executed": False}
    write_json(output / "manifest.json", summary)
    return summary
