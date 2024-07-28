from abc import abstractmethod
from typing import Callable, Iterator, override
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
		self.arg_mapper = ArgMapper()

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
	
	def __call__(self, *raw_args: str, no_sub=False):
		if raw_args:
			scmd = raw_args[0]
			if not no_sub and self.has_subcommand(scmd):
				return self.subcommand(scmd)(*raw_args[1:], no_sub=scmd.endswith("*"))
		
		args, kwargs = self.arg_mapper(*raw_args)

		return self._func(*args, **kwargs)

	@property
	def parent(self) -> "Command | None": return self._parent

	@property
	def arg_mapper(self) -> "ArgMapper": return self._mapper

	@arg_mapper.setter
	def arg_mapper(self, value: "ArgMapper"):
		value.command = self
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

class ArgMapper:
	def __init__(self):
		self._command: Command = None
		self._params: dict[str, inspect.Parameter] = None
		self._kw_params: dict[str, inspect.Parameter] = None
		self._has_kwargs: bool = False
	
	@abstractmethod # should be overriden, as it is the only thing to implement
	def __call__(self, *args: str) -> tuple[list[str], dict[str, any]]:
		return args, {}

	@property
	def command(self) -> Command: return self._command

	@command.setter
	def command(self, value: Command):
		self._command = value
		self._params = dict(value.signature.parameters)
		self._kw_params = {k: v for k, v in self._params.items() if v.kind == inspect.Parameter.KEYWORD_ONLY}
		self._has_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in self._params.values())

	@property
	def params(self) -> dict[str, inspect.Parameter]: return self._params

	@property
	def kw_params(self) -> dict[str, inspect.Parameter]: return self._kw_params

	@property
	def has_kwargs(self) -> bool: return self._has_kwargs

class BoolMapper(ArgMapper):
	def __init__(self, prefix="-", enable_kebab_case=True):
		super().__init__()
		self._prefix = prefix
		self._flag_defaults: dict[str, bool] = None
		self._enable_kebab_case = enable_kebab_case

	def _parse_arg_name(self, arg: str) -> str:
		arg = arg[len(self.prefix):]
		if self.enable_kebab_case:
			arg = arg.replace("-", "_")
		return arg

	@override
	def __call__(self, *args: str) -> tuple[list[str], dict[str, any]]:
		no_parse = [arg for arg in args if not arg.startswith(self.prefix)]
		parse = [self._parse_arg_name(arg) for arg in args if arg.startswith(self.prefix)]
		flags = self.flag_defaults

		for arg in parse:
			if not self.has_kwargs and arg not in flags:
				raise CommandException(f"{self.command.fullname} does not support flag \"{self.prefix}{arg}\"")
			flags[arg] = arg not in flags or not flags[arg]
		
		return no_parse, flags

	@property
	def enable_kebab_case(self) -> bool: return self._enable_kebab_case

	@enable_kebab_case.setter
	def enable_kebab_case(self, value: bool): self._enable_kebab_case = value

	@property
	def prefix(self) -> str: return self._prefix

	@prefix.setter
	def prefix(self, value: str): self._prefix = value

	@property
	def flag_defaults(self) -> dict[str, bool]: return dict(self._flag_defaults)

	@ArgMapper.command.setter
	def command(self, value: Command):
		super(type(self), type(self)).command.fset(self, value) # python...
		self._flag_defaults = {param.name: (param.default if param.default is not inspect._empty else False) for param in self.params.values()}

class StringMapper(ArgMapper):
	def __init__(self, prefix="-", set_token="=", enable_kebab_case=True):
		super().__init__()
		self.prefix = prefix
		self.set_token = set_token
		self.enable_kebab_case = enable_kebab_case
		self._flag_minimum: set[str] = None
		self._flag_maximum: set[str] = None

	def _parse_arg_name(self, arg: str) -> str:
		arg = arg[len(self.prefix):]
		if self.enable_kebab_case:
			arg = arg.replace("-", "_")
		return arg

	def _parse_iter(self, *args: str) -> Iterator[tuple[str, bool]]:
		it = iter(args)
		for arg in it:
			is_flag = arg.startswith(self.prefix)
			if is_flag:
				if self.set_token in arg:
					arg, value = arg.split(self.set_token, 1)
					arg = f"{self._parse_arg_name(arg)}{self.set_token}{value}"
				else:
					try:
						arg = f"{self._parse_arg_name(arg)}{self.set_token}{next(it)}"
					except StopIteration:
						raise CommandException(f"Not enough args for flag {arg}")
			yield arg, is_flag

	@override
	def __call__(self, *args: str) -> tuple[list[str], dict[str, any]]:
		arg_and_flag = list(self._parse_iter(*args))
		flags = dict(arg.split(self.set_token, 1) for arg, is_flag in arg_and_flag if is_flag)

		if self._flag_minimum - flags.keys():
			raise CommandException(f"Missing required flags: {", ".join(self._flag_minimum - flags.keys())}")

		if not self.has_kwargs and flags.keys() - self._flag_maximum:
			raise CommandException(f"Unknown flags: {", ".join(flags.keys() - self._flag_maximum)}")

		return [arg for arg, is_flag in arg_and_flag if not is_flag], flags

	@property
	def enable_kebab_case(self) -> bool: return self._enable_kebab_case

	@enable_kebab_case.setter
	def enable_kebab_case(self, value: bool): self._enable_kebab_case = value

	@property
	def prefix(self) -> str: return self._prefix

	@prefix.setter
	def prefix(self, value: str): self._prefix = value

	@property
	def set_token(self) -> str: return self._set_token

	@set_token.setter
	def set_token(self, value: str): self._set_token = value
	
	@ArgMapper.command.setter
	def command(self, value: Command):
		super(type(self), type(self)).command.fset(self, value)
		self._flag_minimum = {name for name, param in self.kw_params.items() if param.default is inspect._empty}
		self._flag_maximum = set(self.kw_params.keys())

_commands: list[Command] = []
_command_map: dict[str, Command] = {}
_subcommand_map: dict[Command, dict[str, Command]] = {}
_quit = False

# decorator for registering a command
def register(name: str | list[str] | None = None, *, parent: Command | None = None, arg_mapper: ArgMapper = None, on_load: Callable[[], bool] | None = None):
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

			if arg_mapper:
				command.arg_mapper = arg_mapper

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