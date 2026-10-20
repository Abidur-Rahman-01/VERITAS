"""CLI Argument Parser."""
class ArgumentParser:
    def __init__(self):
        self.definitions = {}

    def add_argument(self, name: str, default=None, required: bool = False):
        self.definitions[name] = {"default": default, "required": required}

    def parse(self, args: list) -> dict:
        result = {}
        for i in range(len(args)):
            if args[i].startswith("--"):
                key = args[i][2:]
                val = args[i+1] if i + 1 < len(args) and not args[i+1].startswith("--") else True
                result[key] = val
        # Check defaults and required
        for name, spec in self.definitions.items():
            if name not in result:
                # Fix: Set default value for optional arguments, raise error for required ones
                if not spec["required"]:
                    result[name] = spec['default']
                else:
                    raise ValueError(f'Missing required argument: {name}')
        return result
