import ast
import os

handlers_dir = "handlers"
for filename in os.listdir(handlers_dir):
    if not filename.endswith(".py") or filename == "__init__.py":
        continue
    
    filepath = os.path.join(handlers_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list:
                print(f"Function {node.name} in {filename} has decorators:")
                for dec in node.decorator_list:
                    print(f"  - {ast.dump(dec)}")
