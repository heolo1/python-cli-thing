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

def iscommandfunc(obj: any):
	return hasattr(obj, "command_data")

class CommandData:
	def __init__(self, func: Callable, name: str | list[str], parent: "CommandData | None" = None):
		self.func = func
		self.desc: str | None = None
		self.long_desc: str | None = None
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

		self.flag_mapper = FlagMapper()

		_check_list((name for name in self.names if not _valid_command(name)), "Invalid command name")

		if hasattr(func, "command_processors"):
			for processor in func.command_processors:
				processor(self)

	def __repr__(self):
		return f"Command[{self.fullname()}{"*" if self.aliases else ""}]"
	
	def __call__(self, arg: str | None = None, *raw_args: str):
		if not arg:
			return self.func()
		elif self.has_subcommand(arg):
			return self.subcommand(arg)(*raw_args)
		
		args, kwargs = self.flag_mapper(arg, *raw_args)

		return self.func(*args, **kwargs)

	@property
	def _signature(self) -> inspect.Signature:
		return inspect.signature(self.func)
	
	def print_help_short(self, prefix="", star_subcommands=True):
		print(prefix + self.name, end="")
		if star_subcommands and self.has_subcommands:
			print("*", end="")
		if self.aliases:
			print(f" ({", ".join(self.aliases)})", end="")
		if self.desc:
			print(f" - {self.desc}", end="")
		print()

	def print_help(self, all_subcommands=False):
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
			if all_subcommands:
				for prefix, command in self.all_subcommands:
					command.print_help_short(prefix, False)
			else:
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

	@property
	def all_subcommands(self) -> list[tuple[str, "CommandData"]]:
		return [(prefix, command) for subcommand in self.subcommands 
		  for prefix, command in [("", subcommand)] + [(f"{subcommand.name} {sprefix}", ssubcommand) for sprefix, ssubcommand in subcommand.all_subcommands]]

class CommandException(Exception): ...

class FlagMapper:
	def __init__(self):
		self.params: MappingProxyType[str, inspect.Parameter] = None
	
	@abstractmethod # should be overriden, as it is the only thing to implement
	def __call__(self, *args: str) -> tuple[list[str], dict[str, any]]:
		return args, {}

_commands: list[CommandData] = []
_command_map: dict[str, CommandData] = {}
_subcommand_map: dict[CommandData, dict[str, CommandData]] = {}
_quit = False

# decorator for registering a command
def register(name: str | list[str] | None = None, parent: Callable | CommandData | None = None, *, on_load: Callable[[], bool] | None = None):
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

			command_data = CommandData(func, name, parent)
			command_map = _subcommand_map[parent] if parent else _command_map
			_check_list((name for name in command_data.names if name in command_map), "Command naming conflict")
			if on_load and not on_load():
				raise CommandException(f"Load function of {command_data} failed")

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

def _cmd_deco_wrap(wrapper):
	def outer(*args, **kwargs):
		def inner(func: Callable):
			if iscommandfunc(func):
				wrapper(*args, **kwargs)(func.command_data)
			else:
				if not hasattr(func, "command_processors"):
					func.command_processors = []
				func.command_processors.append(wrapper(*args, **kwargs))
			return func
		return inner
	return outer

@_cmd_deco_wrap
def desc(desc: str | None = None, long_desc: str | None = None):
	def inner(self: CommandData):
		self.desc = desc
		self.long_desc = long_desc
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

def run(command: Callable | str, *args):
	global _command_map
	if iscommandfunc(command):
		command(*args)
	elif isinstance(command, str) and command.lower() in _command_map:
		_command_map[command.lower()](*args)
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