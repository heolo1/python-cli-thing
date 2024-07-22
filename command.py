from typing import Callable
import inspect, time, sys, os

def _valid_command(name: str) -> bool:
	return name and name[0].isalpha() and len(name.split()) == 1 and name.isascii() and name.islower() and "=" not in name and "*" not in name

def _check_list(errs, errstr):
	errs = list(errs)
	if errs:
		raise CommandException(f"{errstr}{"" if len(errs) == 1 else "s"}: " + repr(errs[0] if len(errs) == 1 else errs))
	
def iscommandfunc(obj: any):
	return hasattr(obj, "command_data")

class CommandData:
	def __init__(self, func: Callable, name: str | list[str], *, parent: "CommandData | None" = None, desc: str | None, long_desc: str | None):
		self.func = func
		self.desc = desc
		self.long_desc = long_desc
		self.parent = parent

		# names
		if isinstance(name, str):
			self.name = name
			self.names = [ name ]
			self.aliases = set()
		elif isinstance(name, list):
			self.name = name[0]
			self.names = name
			self.aliases = set(name[1:])

		_check_list((name for name in self.names if not _valid_command(name)), "Invalid command name")

	def __repr__(self):
		return f"Command[{self.fullname()}{"*" if self.aliases else ""}]"
	
	def __call__(self, *args, **kwargs):
		if args and self.has_subcommand(args[0]):
			return self.subcommand(args[0])(*args[1:], **kwargs)
		else:
			return self.func(*args, **kwargs)

	@property
	def _signature(self) -> inspect.Signature:
		return inspect.signature(self.func)
	
	def print_help_short(self):
		print(self.name, end="")
		if self.has_subcommands:
			print("*", end="")
		if self.aliases:
			print(f" ({", ".join(self.aliases)})", end="")
		if self.desc:
			print(f" - {self.desc}", end="")
		print()

	def print_help(self):
		print(self.fullname())
		if self.aliases:
			print(f"Aliases: {", ".join(self.aliases)}")
		if self.parent:
			print(f"Subcommand of {self.parent.fullname()}")
		if self.long_desc:
			print(self.long_desc)
		elif self.desc:
			print(self.desc)
		else:
			print("No description found")
		if self.has_subcommands:
			print("\nSubcommands:")
			for command in self.subcommands:
				command.print_help_short()

	def fullname(self, name: str | None = None):
		if not name:
			name = self.name
		return self.parent.fullname(f"{self.parent.name} {name}") if self.parent else name

	@property
	def has_subcommands(self) -> bool:
		return self in _subcommand_map
	
	def has_subcommand(self, command):
		return self.has_subcommands and command in _subcommand_map[self]
	
	@property
	def subcommands(self) -> list["CommandData"]:
		return list(set(_subcommand_map[self].values())) if self.has_subcommands else []

	def subcommand(self, command):
		return _subcommand_map[self][command]

class CommandException(Exception): ...

_commands: list[CommandData] = []
_command_map: dict[str, CommandData] = {}
_subcommand_map: dict[CommandData, dict[str, CommandData]] = {}
_quit = False

# decorator for registering a command
def register(name: str | list[str] | None = None, *, parent: Callable | CommandData | None = None, desc: str | None = None, long_desc: str | None = None):
	aname = name
	aparent = parent
	def inner(func: Callable):
		name = aname if aname else func.__name__
		parent = aparent
		
		try:
			if parent:
				if iscommandfunc(parent):
					parent = parent.command_data
				if not isinstance(parent, CommandData):
					raise CommandException(f"Invalid parent: {parent} is not a command function or CommandData")
				_subcommand_map.setdefault(parent, {})

			command_data = CommandData(func, name, parent=parent, desc=desc, long_desc=long_desc)
			command_map = _subcommand_map[parent] if parent else _command_map
			_check_list((name for name in command_data.names if name in command_map), "Command naming conflict")

			# no errors should occur after this
			func.command_data = command_data
			_commands.append(command_data)
			for name in command_data.names:
				_command_map[command_data.fullname(name)] = command_data
				if parent:
					_subcommand_map[parent][name] = command_data

			print(f"Registered {command_data}")
		except CommandException as e:
			print(f"Could not register command {func} ({name})")
			print(e)

			# clean up subcommand dicts
			if parent in _subcommand_map and not _subcommand_map[parent]:
				del _subcommand_map[parent]

			# we do not need to clean up anything else, since all major changes were made after any error zones

		return func
	return inner

@register(desc="Shows the help menu.",
		long_desc="Displays a description of the command.\nRun \"help <command name>\" to view a further description of a command.")
def help(command=None, *args):
	global _commands, _command_map
	
	if not command:
		print("COMMANDS")
		for command in _commands:
			command.print_help_short()
	elif iscommandfunc(command):
		command.command_data.print_help()
	elif isinstance(command, CommandData):
		command.print_help()
	elif command in _command_map:
		# start searching through commands and subcommands
		for arg in args:
			if command + " " + arg in _command_map:
				command = _command_map[command + " " + arg].fullname()
			else:
				_command_map[command].print_help()
				raise CommandException(f"{arg} - Unknown subcommand")
		_command_map[command].print_help()			
	else:
		raise CommandException(f"{command} - Unknown command\nRun \"help\" to view a list of commands.")

@register(["quit", "exit", "close"],
		desc="Quit the command prompt.",
		long_desc="Quits the command prompt and saves everything as necessary.")
def quit():
	global _quit
	_quit = True
	print("Stopping...")

@register(["reload", "rel"],
		desc="Reload the program.",
		long_desc="Reloads the program with the same arguments supplied.\nThis is mainly for development purposes.")
def reload():
	run(quit)
	print(f"[{time.ctime(time.time())}] Reloading...")
	os.execl(sys.executable, sys.executable, *sys.argv)

@register(desc="Test",long_desc="Test Test")
def test(*args, **kwargs):
	print("hi", args, kwargs)

@register("a", parent=test, desc="test a", long_desc="Test Test Test")
def test_a(*args, **kwargs):
	print("hi a", args, kwargs)

def run(command: Callable | str, *args, **kwargs):
	global _command_map
	if iscommandfunc(command):
		command(*args, **kwargs)
	elif isinstance(command, str) and command.lower() in _command_map:
		_command_map[command.lower()](*args, **kwargs)
	else:
		raise CommandException(f"Invalid command: {command}\nRun \"help\" to see list of commands")

def main():
	global _quit
	_quit = False
	while True:
		command = input("> ")
		if not command:
			continue

		allargs = command.strip().split(" ")

		try:
			run(allargs[0],
				*[arg for arg in allargs[1:] if "=" not in arg], 
				**{arg.split("=", 1)[0]: arg.split("=", 1)[1] for arg in allargs[1:] if "=" in arg})
		except CommandException as e:
			print("Error:", e)
		except TypeError as e:
			print("TypeError:", e)

		if _quit:
			break