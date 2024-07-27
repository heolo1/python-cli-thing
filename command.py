from abc import abstractmethod
from typing import Callable
from types import MappingProxyType
import inspect, time, sys, os

def _valid_command(name: str) -> bool:
	return _valid_word(name) and "*" not in name

def _valid_word(word: str) -> bool:
	return word and len(word.split()) == 1 and word.isascii()

def _check_list(errs, errstr):
	errs = list(errs)
	if errs:
		raise CommandException(f"{errstr}{"" if len(errs) == 1 else "s"}: " + repr(errs[0] if len(errs) == 1 else errs))

def istruthy(word: str) -> bool:
	return word.lower() in ["y", "yes", "true"]

class Command:
	def __init__(self, func: Callable, name: str | list[str], parent: "Command | None" = None):
		self._func = func
		self._desc: str | None = None
		self._long_desc: str | None = None
		self._parent = parent
		self.flag_mapper = FlagMapper()

		# names
		if isinstance(name, str):
			self._name = name
			self._names = [ name ]
			self._aliases = set()
		elif isinstance(name, list):
			self._name = name[0]
			self._names = name
			self._aliases = set(name[1:])

		_check_list((name for name in self.names if not _valid_command(name)), "Invalid command name")

		if hasattr(func, "command_processors"):
			for processor in func.command_processors:
				processor(self)
			del func.command_processors

	def __repr__(self):
		return f"Command[{self.fullname}{"*" if self.aliases else ""}]"
	
	def __call__(self, arg: str | None = None, *raw_args: str, no_sub=False):
		if not arg:
			return self._func()
		elif not no_sub and self.has_subcommand(arg):
			return self.subcommand(arg)(*raw_args, no_sub=arg.endswith("*"))
		
		args, kwargs = self.flag_mapper(arg, *raw_args)

		return self._func(*args, **kwargs)

	@property
	def parent(self) -> "Command | None": return self._parent

	@property
	def flag_mapper(self) -> "FlagMapper": return self._mapper

	@flag_mapper.setter
	def flag_mapper(self, value: "FlagMapper"):
		value._params = self.signature.parameters
		self._mapper = value

	@property
	def name(self) -> str: return self._name
	
	@property
	def names(self) -> list[str]: return self._names[:]

	@property
	def aliases(self) -> set[str]: return set(self._aliases)
	
	@property
	def description(self) -> str | None: return self._desc
	
	@description.setter
	def description(self, value: str): self._desc = value

	@property
	def long_description(self) -> str | None: return self._long_desc
	
	@long_description.setter
	def long_description(self, value: str): self._long_desc = value

	@property
	def has_subcommands(self) -> bool: return self in _subcommand_map

	@property
	def subcommands(self) -> list["Command"]: return list(set(_subcommand_map[self].values())) if self.has_subcommands else []

	@property
	def all_subcommands(self) -> list[tuple[str, "Command"]]:
		return [(prefix, command) for subcommand in self.subcommands 
		  for prefix, command in [("", subcommand)] + [(f"{subcommand.name} {sprefix}", ssubcommand) for sprefix, ssubcommand in subcommand.all_subcommands]]

	@property
	def signature(self) -> inspect.Signature: return inspect.signature(self._func)
	
	@property
	def parent_prefix(self) -> str: return f"{self.parent.parent_prefix}{self.parent.name} " if self.parent else ""

	@property
	def fullname(self): return f"{self.parent_prefix}{self.name}"

	def print_help_short(self, prefix="", star_subcommands=True):
		print(prefix + self.name, end="")
		if star_subcommands and self.has_subcommands:
			print("*", end="")
		if self.aliases:
			print(f" ({", ".join(self.aliases)})", end="")
		if self.description:
			print(f" - {self.description}", end="")
		print()

	def print_help(self, all_subcommands=False):
		print(self.fullname)
		if self.aliases:
			print(f"Aliases: {", ".join(self.aliases)}")
		if self.parent:
			print(f"Subcommand of {self.parent.fullname}")
		if self.long_description:
			print(self.long_description)
		elif self.description:
			print(self.description)
		else:
			print("No description found")
		if self.has_subcommands:
			print("\nSubcommands:")
			if all_subcommands:
				for prefix, command in self.all_subcommands:
					command.print_help_short(prefix, False)
			else:
				for command in self.subcommands:
					command.print_help_short()

	def has_subcommand(self, command):
		return self.has_subcommands and (command in _subcommand_map[self] or command.endswith("*") and command[:-1] in _subcommand_map[self])
	
	def subcommand(self, command):
		return _subcommand_map[self][command[:-1] if command.endswith("*") else command]

class CommandException(Exception): ...

class FlagMapper:
	def __init__(self):
		self._params: MappingProxyType[str, inspect.Parameter] = None
	
	@abstractmethod # should be overriden, as it is the only thing to implement
	def __call__(self, *args: str) -> tuple[list[str], dict[str, any]]:
		return args, {}

_commands: list[Command] = []
_command_map: dict[str, Command] = {}
_subcommand_map: dict[Command, dict[str, Command]] = {}
_quit = False

# decorator for registering a command
def register(name: str | list[str] | None = None, parent: Command | None = None, *, on_load: Callable[[], bool] | None = None):
	aname = name
	aparent = parent
	def inner(func: Callable) -> Callable | Command:
		name = aname if aname else func.__name__
		parent = aparent
		
		try:
			if parent and isinstance(parent, Command):
				_subcommand_map.setdefault(parent, {})
			elif parent:
				raise CommandException(f"Invalid parent: {parent} is not a command function or CommandData")

			command = Command(func, name, parent)
			command_map = _subcommand_map[parent] if parent else _command_map
			_check_list((name for name in command.names if name in command_map), "Command naming conflict")
			if on_load and not on_load():
				raise CommandException(f"Load function of {command} failed")

			# no errors should occur after this
			_commands.append(command)
			for name in command.names:
				_command_map[command.parent_prefix + name] = command
				if parent:
					_subcommand_map[parent][name] = command

			print(f"Registered {command}")
			return command
		except CommandException as e:
			print(f"Could not register command {func} ({name})")
			print(e)

			# clean up subcommand dicts
			if parent in _subcommand_map and not _subcommand_map[parent]:
				del _subcommand_map[parent]

			# we do not need to clean up anything else, since all major changes were made after any error zones

		return func
	return inner

def _cmd_deco_wrap(wrapper):
	def outer(*args, **kwargs):
		def inner(command: Command | Callable):
			if isinstance(command, Command):
				wrapper(*args, **kwargs)(command)
			else:
				if not hasattr(command, "command_processors"):
					command.command_processors = []
				command.command_processors.append(wrapper(*args, **kwargs))
			return command
		return inner
	return outer

@_cmd_deco_wrap
def desc(desc: str | None = None, long_desc: str | None = None):
	def inner(self: Command):
		self.description = desc
		self.long_description = long_desc
	return inner

@register()
@desc("Shows the help menu.",
	  "Displays a description of the command.\nRun \"help <command name>\" to view a further description of a command.")
def help(command=None, *args):
	global _commands, _command_map
	
	if not command:
		print("COMMANDS")
		for command in _commands:
			command.print_help_short()
	elif isinstance(command, Command):
		command.print_help()
	elif command.lower() in _command_map:
		# start searching through commands and subcommands
		command = _command_map[command.lower()]
		for arg in args:
			if command.has_subcommand(arg.lower()):
				command = command.subcommand(arg.lower())
			else:
				command.print_help()
				raise CommandException(f"{arg} - Unknown subcommand")
		command.print_help()
	else:
		raise CommandException(f"{command} - Unknown command\nRun \"help\" to view a list of commands.")

@register(["quit", "exit", "close"])
@desc("Quit the command prompt.",
	  "Quits the command prompt and saves everything as necessary.")
def quit():
	global _quit
	_quit = True
	print("Stopping...")

@register(["reload", "rel"])
@desc("Reload the program.",
	  "Reloads the program with the same arguments supplied.\nThis is mainly for development purposes.")
def reload():
	run(quit)
	print(f"[{time.ctime(time.time())}] Reloading...")
	os.execl(sys.executable, sys.executable, *sys.argv)

@register(["clear", "cls"])
@desc("Clears the terminal.",
	  "Clears the terminal of all text.")
def clear():
	print("\033c")

def run(command: Command | str, *args):
	global _command_map
	if isinstance(command, Command):
		command(*args)
	elif isinstance(command, str) and command.lower() in _command_map:
		_command_map[command.lower()](*args)
	elif isinstance(command, str) and command.endswith("*") and command[:-1].lower() in _command_map:
		_command_map[command[:-1].lower()](*args, no_sub=True)
	else:
		raise CommandException(f"Invalid command: {command}\nRun \"help\" to see list of commands")

def main():
	global _quit
	_quit = False
	while True:
		command = input("> ").strip()
		if not command:
			continue

		try:
			run(*command.split())
		except CommandException as e:
			print("Error:", e)
		except TypeError as e:
			print("TypeError:", e)

		if _quit:
			break

if __name__ == "__main__":
	main()