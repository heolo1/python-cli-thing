import command, random

def on_load() -> bool:
	global value1
	value1 = random.randint(1, 100)
	print("Set value")
	return True

@command.register(["example", "ex"], on_load=on_load)
@command.desc("An example command.", "An example command. Prints out all arguments supplied to it.")
def example(*args):
	print(f"# Args: {len(args)}")
	for i in range(len(args)):
		print(f"Arg {i} - {args[i]}")

def on_load2() -> bool:
	global value2
	value2 = random.randint(1, 100)
	print("Set value2")
	return True

@command.register(parent=example, arg_mapper=command.BoolMapper(), on_load=on_load2)
@command.desc("Prints the numbers generated.", "Prints the numbers randomly generated on load.")
def value(*, a = True, b, other_arg):
	print(f"{value1=}")
	print(f"{value2=}")
	print(f"{a=}, {b=}, {other_arg=}")

@command.register("print", parent=example, arg_mapper=command.StringMapper())
@command.desc("Prints out the supplied arguments.", "Prints out the values of all of the supplied flags and values.")
def p(*, a="hello", b, c, d="something else"):
	print(f"{a=}, {b=}, {c=}, {d=}")

@command.register(parent=example, arg_mapper=command.TypeMapper())
def types(*, a: int, b: int = 5, c: bool):
	print(f"{a=}, {b=}, {c=}")

def main():
	command.main()

if __name__ == "__main__":
	main()