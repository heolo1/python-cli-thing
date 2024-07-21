from abc import abstractmethod
from typing import override, Callable
import inspect, sys

class Command:
	...

class SubCommand(Command):
	...

def findclass(func):
    cls = sys.modules.get(func.__module__)
    if cls is None:
        return None
    for name in func.__qualname__.split('.')[:-1]:
        cls = getattr(cls, name)
    if not inspect.isclass(cls):
        return None
    return cls

class Command:
	@staticmethod
	def sub(arg: str | list[str] | Callable | type | None = None, description: str | None = None, long_description: str | None = None):
		if isinstance(arg, type):
			global _sub_commands, _sub_command_map
			_sub_commands[arg] = []
			_sub_command_map[arg] = {}
			for _, func in inspect.getmembers(arg, inspect.isfunction):
				if hasattr(func, "_is_subcommand"):
					add_command(SubCommand(func, func._subcommand_name, description=func._subcommand_description, long_description=func._subcommand_long_description),
				 		_sub_commands[arg], _sub_command_map[arg])
			if not _sub_commands[arg]:
				del _sub_commands[arg]
				del _sub_command_map[arg]
			return arg
		elif isinstance(arg, Callable):
			arg._is_subcommand = True
			arg._subcommand_name = arg.__name__
			arg._subcommand_description = description
			arg._subcommand_long_description = long_description
			return arg
		else:
			def wrapper(f: callable):
				f._is_subcommand = True
				f._subcommand_name = arg if arg else f.__name__
				f._subcommand_description = description
				f._subcommand_long_description = long_description
				return f
			return wrapper

	def __init__(self, name: str | list[str], *, description: str | None = None, long_description: str | None = None):
		if isinstance(name, str):
			self.name = name.lower()
			self.names = { self.name }
			self.aliases: set[str] = set()
		elif isinstance(name, list) and len(name) > 0:
			self.name = name[0].lower()
			self.names = set(map(str.lower, name))
			self.aliases = self.names - { self.name }
		else:
			raise AssertionError(f"Invalid name ({name})")

		self.description = description
		self.long_description = long_description
	
	def __repr__(self) -> str:
		return f"Command[{self.name}{f", ({"|".join(self.aliases)})" if self.aliases else ""}]"

	def __call__(self, subcommand=None, *args, **kwargs) -> bool:
		if self.has_subcommand(subcommand):
			return _sub_command_map[type(self)][subcommand](self, *args, **kwargs)
		else:
			return self._consume(*([subcommand] if subcommand else []), *args, **kwargs)
		
	def conflicts(self, command: Command) -> bool:
		return len(self.names & command.names) > 0
	
	@abstractmethod
	def _on_add(self) -> bool:
		return True

	@abstractmethod
	def _consume(self, *args, **kwargs) -> bool:
		print(f"Command: {self.name}")
		print(f"Args: {args}")
		print(f"Kwargs: {kwargs}")
		return True
	
	def _get_consume_signature(self) -> inspect.Signature:
		return inspect.signature(self._consume)

	def print_help_short(self):
		print(self.name, end="")
		if self.has_subcommands():
			print("*", end="")
		if self.aliases:
			print(f" ({", ".join(self.aliases)})", end="")
		if self.description:
			print(f" - {self.description}", end="")
		print()

	def print_help(self):
		print(f"Usage: {self.name}")
		if self.aliases:
			print(f"Aliases: {", ".join(self.aliases)}")
		if self.long_description:
			print(self.long_description)
		elif self.description:
			print(self.description)
		if self.has_subcommands():
			print("\nSubcommands:")
			self.print_subcommands()

	def has_subcommands(self) -> bool:
		return type(self) in _sub_commands and bool(self.get_subcommands())
	
	def has_subcommand(self, command=None):
		return self.has_subcommands() and command in _sub_command_map[type(self)]
	
	def get_subcommands(self) -> list[Command]:
		return _sub_commands[type(self)]
	
	def print_subcommands(self):
		for command in self.get_subcommands():
			command.print_help_short()

class SubCommand(Command):
	def __init__(self, func: callable, name: str | list[str] | None = None, description: str | None = None, long_description: str | None = None):
		super().__init__(name if name else func.__name__, description=description, long_description=long_description)
		self.func = func

	def __repr__(self) -> str:
		return f"SubCommand[{self.name}{f", ({"|".join(self.aliases)})" if self.aliases else ""}]"
	
	@override
	def _consume(self, *args, **kwargs) -> bool:
		return self.func(*args, **kwargs)

_commands: list[Command] = []
_command_map: dict[str, Command] = {}
_sub_commands: dict[type, list[SubCommand]] = {}
_sub_command_map: dict[type, dict[str, SubCommand]] = {}
_quit = False

def _can_add_command(command: Command, command_list: list[Command] = _commands, command_map: dict[str, Command] =_command_map) -> bool:
	if any(name in command_map for name in command.names):
		print(f" -> Could not add command {command} (Conflicts: {[c for c in command_list if c.conflicts(command)]})")
		return False
	elif not command._on_add():
		print(f" -> Could not add command {command} (Failed on_add)")
		return False
	return True

def add_command(command: Command, command_list=_commands, command_map=_command_map) -> bool:
	print(f"Adding {command}")
	if _can_add_command(command, command_list, command_map):
		command_list.append(command)
		for name in command.names:
			command_map[name] = command
		return True
	return False

class Quit(Command):
	def __init__(self):
		super().__init__(["quit", "exit", "close"], description="Quit the command prompt.", long_description="Quits the command prompt and saves everything as necessary.")

	@override
	def _consume(self) -> bool:
		global _quit
		_quit = True
		print("Stopping run_commands...")
		return True

class Help(Command):
	def __init__(self):
		super().__init__(["help", "?"], description="Shows the help menu.", long_description="Displays a description of the command.\nRun \"help <command name>\" to view a further description of a command.")

	@override
	def _consume(self, command=None, sub_command=None) -> bool:
		global _commands, _command_map
		
		command = command.lower() if command else command
		sub_command = sub_command.lower() if sub_command else sub_command

		if not command:
			print("COMMANDS")
			for command in _commands:
				command.print_help_short()
		elif command not in _command_map:
			print(f"{command} - Unknown command")
			print("Run \"help\" to view a list of commands.")
			return False
		elif not sub_command:
			_command_map[command].print_help()
		elif not _command_map[command].has_subcommand(sub_command):
			print(f"Invalid subcommand - {command} {sub_command}")
			_command_map[command].print_help()
			return False
		else:
			_sub_command_map[type(_command_map[command])][sub_command].print_help()
		return True

add_command(Quit())
add_command(Help())

def run_command(command: Command | str, *args, **kwargs) -> bool:
	global _command_map
	if issubclass(type(command), Command):
		return command(*args, **kwargs)
	elif type(command) == str and command.lower() in _command_map:
		return _command_map[command.lower()](*args, **kwargs)
	else:
		print(f"Invalid command: {command}")
		print("Run \"help\" to see list of commands")
		return False

def run_commands():
	global _quit
	_quit = False
	while True:
		command = input("> ")
		if not command:
			continue

		allargs = command.strip().split(" ")

		if not run_command(allargs[0],
			*[arg for arg in allargs[1:] if "=" not in arg], 
			**{arg.split("=", 1)[0]: arg.split("=", 1)[1] for arg in allargs[1:] if "=" in arg}):
			print("ERR")
		if _quit:
			break
	