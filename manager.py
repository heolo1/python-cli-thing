import command, api as _

@command.register()
@command.desc("Clears the terminal.")
def clear():
	print("\033c")

def main():
	command.main()

if __name__ == "__main__":
	main()