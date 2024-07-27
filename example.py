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

@command.register(parent=example, on_load=on_load2)
@command.desc("Prints the numbers generated.", "Prints the numbers randomly generated on load.")
def value():
	print(f"value1: {value1}")
	print(f"value2: {value2}")

def main():
	command.main()

if __name__ == "__main__":
	main()