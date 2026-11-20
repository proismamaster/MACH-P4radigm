"""Riduce il file di un agente al solo codice del suo ruolo (consiglio dei mentor: file piccoli = deploy più veloce).

Uso, dalla cartella della repo:
    python tools/riduci_agente.py asst/gp/agent/agent.py gp "_gp(city, message, chat)"
    python tools/riduci_agente.py asst/booking_centre/agent/agent.py booking_centre "_booking_centre(city, message, chat)"
Poi SEMPRE: python tools/confronto_riduzione.py <repo> <ruolo> <file completo salvato> <file ridotto>
e tutti i test. Se il confronto dice DIVERSO, non pubblicare.

Remove top-level functions/classes unreachable from main/handle/role_of after narrowing handle to one role."""
import ast, re, sys
path, role, call = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding="utf-8").read()
start = src.index('    if role == "gp":\n        await _gp(city, message, chat)')
end = src.index("# --- shared")
new = ("    # This file serves only its own role: the other roles' code was removed to keep the\n"
       "    # brain small for the city's deploy scan (see team/DECISIONS.md).\n"
       f'    if role == "{role}":\n        await {call}\n\n\n')
src = src[:start] + new + src[end:]
src = src.replace('    if hold_self:\n        await _advance(city, message, chat, fixed="CONS-GIN", replacing=True)\n', '')
tree = ast.parse(src)
defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
def refs(node):
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name)} | {x.attr for x in ast.walk(node) if isinstance(x, ast.Attribute)}
keep, todo = set(), ["main", "handle", "role_of"]
for n in tree.body:
    if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        todo += list(refs(n))
while todo:
    name = todo.pop()
    if name in defs and name not in keep:
        keep.add(name); todo += list(refs(defs[name]))
drop = [n for n in defs if n not in keep]
lines = src.splitlines(keepends=True)
for s, e in sorted(((defs[n].decorator_list[0].lineno if defs[n].decorator_list else defs[n].lineno) - 1, defs[n].end_lineno) for n in drop)[::-1]:
    del lines[s:e]
out = re.sub(r"\n{4,}", "\n\n\n", "".join(lines))
ast.parse(out)
open(path, "w", encoding="utf-8").write(out)
print("rimosse", len(drop), sorted(drop))
